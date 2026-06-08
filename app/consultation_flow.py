from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .knowledge import KnowledgeHit, search_knowledge


MAX_EXTERNAL_RAG_CHARS = 3900


STAGE_LABELS = {
    "chief": "主诉确认",
    "symptoms": "症状细化",
    "duration_trigger": "病程与诱因",
    "history": "用药检查与既往史",
    "red_flag": "危险信号判断",
    "summary": "阶段性总结",
}

NOSE_TERMS = [
    "鼻塞",
    "流鼻涕",
    "流涕",
    "喷嚏",
    "打喷嚏",
    "鼻痒",
    "嗅觉",
    "鼻涕",
    "鼻出血",
    "流鼻血",
    "鼻血",
    "鼻子流血",
    "鼻炎",
    "过敏性鼻炎",
    "鼻窦炎",
    "慢性鼻窦炎",
    "鼻息肉",
]
THROAT_TERMS = ["嗓子", "喉咙", "咽喉", "咽痛", "咽干", "咽痒", "异物感", "声音嘶哑", "吞咽", "痰"]
EAR_TERMS = ["耳闷", "耳鸣", "耳痛", "耳朵", "听力"]
SLEEP_TERMS = ["打鼾", "憋醒", "呼噜", "睡眠呼吸暂停"]
DURATION_RE = re.compile(
    r"(\d+\s*(?:天|周|个?星期|个?礼拜|月|年)|[一二两三四五六七八九十半]+(?:天|周|个?星期|个?礼拜|月|年)|几天|几年|长期|反复|从小)"
)

SLOT_STAGE = {
    "chief": "chief",
    "nose_duration": "duration_trigger",
    "nose_discharge": "symptoms",
    "nose_trigger": "duration_trigger",
    "nose_red_flags": "red_flag",
    "throat_duration": "duration_trigger",
    "throat_quality": "symptoms",
    "throat_red_flags": "red_flag",
    "throat_lifestyle": "duration_trigger",
    "nosebleed_control": "red_flag",
    "ear_duration": "duration_trigger",
    "ear_detail": "symptoms",
    "ear_red_flags": "red_flag",
    "sleep_detail": "symptoms",
    "medication": "history",
    "exam_history": "history",
    "urgent": "red_flag",
}

SLOT_QUESTIONS = {
    "chief": "你现在最主要的不舒服是什么？",
    "nose_duration": "鼻子不舒服持续几天了？",
    "nose_discharge": "鼻涕是清水样，还是黄脓鼻涕？",
    "nose_trigger": "接触灰尘、花粉或冷空气后，会明显加重吗？",
    "nose_red_flags": "有没有发热、明显头痛、鼻出血或视力变化？",
    "throat_duration": "嗓子不舒服持续几天了？",
    "throat_quality": "主要是疼、干，还是有异物感？",
    "throat_red_flags": "有没有发热、吞咽明显疼痛或呼吸不顺？",
    "throat_lifestyle": "最近有熬夜、吃辣，或者用嗓比较多吗？",
    "nosebleed_control": "这次流鼻血现在按压能止住吗？",
    "ear_duration": "耳朵不舒服持续几天了？",
    "ear_detail": "主要是耳闷、耳痛，还是听力下降？",
    "ear_red_flags": "有没有明显头晕、发热、耳朵流脓或听力突然下降？",
    "sleep_detail": "是单纯打鼾，还是睡觉会憋醒、白天犯困？",
    "medication": "这次自己用过什么药或含片吗？",
    "exam_history": "之前做过鼻内镜、过敏原或鼻窦 CT 检查吗？",
    "urgent": "你描述的情况有危险信号，建议尽快线下急诊或耳鼻喉专科处理。",
}


@dataclass
class ConsultationTurn:
    user_text: str
    stage: str
    stage_label: str
    next_question: str
    direct_response: str
    external_rag: str
    update_config: dict
    hit_sources: list[str]


@dataclass
class ConsultationOrchestrator:
    profile: dict
    turn_count: int = 0
    facts: dict[str, str] = field(default_factory=dict)
    user_history: list[str] = field(default_factory=list)
    pending_slot: str | None = None
    asked_slots: set[str] = field(default_factory=set)

    def start_dialog_config(self) -> dict:
        return {
            "bot_name": self._doctor_display_name(),
            "system_role": self._base_system_role(),
            "speaking_style": self._speaking_style(),
        }

    def prepare_turn(self, user_text: str) -> ConsultationTurn:
        normalized = _clean_text(user_text)
        self.turn_count += 1
        self.user_history.append(normalized)
        self.user_history = self.user_history[-8:]
        self._extract_facts(normalized)

        direct_answer = _looks_like_medical_info_question(normalized)
        if direct_answer:
            next_slot = None
            stage = "summary"
            next_question = "不要追问，直接回答患者本轮关于检查、处理、用药类别或就医准备的问题。"
        else:
            next_slot = self._next_slot(normalized)
            stage = SLOT_STAGE.get(next_slot or "summary", "summary")
            next_question = self._question_for_slot(next_slot)
        hits = search_knowledge(normalized, top_k=5)
        self._set_pending_slot(next_slot, next_question)
        direct_response = (
            self._medical_info_direct_response(normalized, hits) if direct_answer else self._direct_response(stage, next_question)
        )
        external_rag = self._build_external_rag(normalized, stage, next_question, hits)
        dynamic_role = self._dynamic_system_role(stage, next_question, hits)
        return ConsultationTurn(
            user_text=normalized,
            stage=stage,
            stage_label=STAGE_LABELS.get(stage, stage),
            next_question=next_question,
            direct_response=direct_response,
            external_rag=external_rag,
            update_config={
                "dialog": {
                    "bot_name": self._doctor_display_name(),
                    "system_role": dynamic_role,
                    "speaking_style": self._speaking_style(),
                }
            },
            hit_sources=[hit.source for hit in hits],
        )

    def prepare_voice_rag_turn(self, user_text: str) -> ConsultationTurn:
        normalized = _clean_text(user_text)
        self.turn_count += 1
        self.user_history.append(normalized)
        self.user_history = self.user_history[-8:]
        self._extract_facts(normalized)

        next_slot = self._next_slot(normalized)
        stage = SLOT_STAGE.get(next_slot or "summary", "summary")
        next_question = self._question_for_slot(next_slot)
        self._set_pending_slot(next_slot, next_question)
        hits = search_knowledge(normalized, top_k=5)
        external_rag = self._build_voice_external_rag(normalized, stage, next_question, hits)
        return ConsultationTurn(
            user_text=normalized,
            stage=stage,
            stage_label=STAGE_LABELS.get(stage, stage),
            next_question=next_question,
            direct_response="",
            external_rag=external_rag,
            update_config={},
            hit_sources=[hit.source for hit in hits],
        )

    def _doctor_display_name(self) -> str:
        name = self.profile.get("name") or "医生"
        title = self.profile.get("title") or "医生"
        if name.endswith("医生"):
            return name
        return f"{name}医生" if name != "医生" else title

    def _base_system_role(self) -> str:
        specialty = self.profile.get("specialty") or "耳鼻咽喉科常见疾病"
        return (
            f"你以{self._doctor_display_name()}的口吻进行耳鼻咽喉科语音问诊，专业方向是{specialty}。"
            "你现在是在和患者通电话，不是在写文章。说话自然、沉稳、直接，用医生查房和门诊沟通的语气。"
            "问诊阶段每轮只问一个最关键的问题，最多两句话，说完问题立刻停下来等患者回答。"
            "不要一次连续罗列多个问题，不要把持续时间、诱因、用药和危险信号挤在同一轮里。"
            "先识别患者说的是鼻部、咽喉、耳部还是睡眠相关问题，再按对应主诉逐步收集持续时间、症状性质、诱因、用药经过和危险信号。"
            "信息不足时不要急着下结论，至少经过两到三轮追问后再做阶段性分析。"
            "回答要依据系统随后提供的外部资料和已收集病史，不要编造检查结果。"
            "病史相对充分、没有危险信号时，可以给出更明确的临床倾向，例如目前更符合哪一类常见问题，并说明判断依据和处理方向。"
            "处方药具体剂量和疗效承诺需要医生结合检查确认，语音端不要直接承诺治愈或保证疗效。"
            "遇到呼吸困难、意识异常、持续高热、剧烈头痛、反复大量出血、明显视力或神经症状时，直接建议尽快线下急诊或专科就医。"
            "不要使用列表、编号、加粗或书面报告格式，保持口语化；普通追问尽量只出现一个问号。"
        )

    def _dynamic_system_role(self, stage: str, next_question: str, hits: list[KnowledgeHit]) -> str:
        if next_question and not next_question.endswith("？"):
            facts = self._facts_summary()
            return (
                f"{self._base_system_role()} 已收集信息：{facts} "
                f"当前任务：{next_question} "
                "回答要有临床倾向、判断依据和下一步处理重点；可以提常见检查或用药类别。"
                "不要编造患者没有提供的检查结果，不要给处方药具体剂量或疗效保证。"
                "本轮不要反问患者，不要在结尾追加追问，回答中不要出现问号。"
                "保持口语化，长度控制在三到五句话。"
            )
        stage_rule = {
            "chief": "当前任务是确认主诉，只问患者最主要的不舒服。",
            "symptoms": "当前任务是细化一个症状点，不展开成症状清单。",
            "duration_trigger": "当前任务是在病程和诱因里只补一个缺口。",
            "history": "当前任务是在用药、检查或既往史里只补一个缺口。",
            "red_flag": "当前任务是先排查一个最重要的危险信号组合；如患者有明显危险信号，直接建议线下急诊或尽快专科就医。",
            "summary": "当前任务是做简短阶段性分析，必要时只给一个下一步建议。",
        }.get(stage, "当前任务是继续完成耳鼻咽喉科问诊。")
        facts = self._facts_summary()
        return (
            f"{self._base_system_role()} 已收集信息：{facts} {stage_rule} "
            f"本轮唯一允许追问的问题是：{next_question} "
            "如果这句话是问句，你必须只问这一句；可以有一句很短的承接，但禁止追加第二个问句。"
            "不要追加其他问题，也不要把别的主诉轨道问题带进来，除非它们正是本轮唯一问题。"
            "普通追问总长度尽量不超过35个汉字。"
        )

    def _speaking_style(self) -> str:
        traits = "、".join(self.profile.get("style_traits", []))
        if not traits:
            traits = "先安抚情绪，再解释问题；用词朴素，不夸张；习惯先说需要补充哪一个信息"
        return f"{traits}。语速平稳，回答简短；问诊追问每轮只问一个问题。"

    def _next_slot(self, text: str) -> str | None:
        if _has_any(text, ["呼吸困难", "喘不上", "意识", "昏迷", "大量出血", "止不住血", "止不住", "视力下降", "复视", "剧烈头痛"]):
            return "urgent"

        area = self.facts.get("complaint_area")
        if area == "鼻部" and _has_any(text, ["鼻出血", "流鼻血", "鼻血", "鼻子流血"]) and "nosebleed_control" not in self.asked_slots:
            return "nosebleed_control"
        if not area:
            return "chief"
        if area == "咽喉":
            return self._next_throat_slot()
        if area == "鼻部":
            return self._next_nose_slot()
        if area == "耳部":
            return self._next_ear_slot()
        if area == "睡眠":
            return self._next_sleep_slot()
        return "chief"

    def _next_throat_slot(self) -> str | None:
        if "duration" not in self.facts:
            return "throat_duration"
        if "throat_quality" not in self.facts:
            return "throat_quality"
        if "red_flags" not in self.facts:
            return "throat_red_flags"
        if "throat_lifestyle" not in self.facts:
            return "throat_lifestyle"
        if "medication" not in self.facts:
            return "medication"
        return None

    def _next_nose_slot(self) -> str | None:
        if "duration" not in self.facts:
            return "nose_duration"
        if "discharge" not in self.facts and _has_any(self.facts.get("symptoms", ""), ["鼻塞", "流鼻涕", "流涕", "鼻涕"]):
            return "nose_discharge"
        if "trigger" not in self.facts:
            return "nose_trigger"
        if "red_flags" not in self.facts:
            return "nose_red_flags"
        if "medication" not in self.facts:
            return "medication"
        if "history" not in self.facts:
            return "exam_history"
        return None

    def _next_ear_slot(self) -> str | None:
        if "duration" not in self.facts:
            return "ear_duration"
        if "ear_detail" not in self.facts:
            return "ear_detail"
        if "red_flags" not in self.facts:
            return "ear_red_flags"
        if "medication" not in self.facts:
            return "medication"
        return None

    def _next_sleep_slot(self) -> str | None:
        if "sleep_detail" not in self.facts:
            return "sleep_detail"
        return None

    def _question_for_slot(self, slot: str | None) -> str:
        if not slot:
            return "我先帮你把目前情况简单归纳一下。"
        return SLOT_QUESTIONS.get(slot, "我再补问一个关键信息。")

    def _set_pending_slot(self, slot: str | None, question: str) -> None:
        if slot and question.endswith("？"):
            self.pending_slot = slot
            self.asked_slots.add(slot)
            return
        self.pending_slot = None

    def _direct_response(self, stage: str, next_question: str) -> str:
        if next_question.endswith("？"):
            return next_question
        if stage == "red_flag" and next_question:
            return next_question
        if stage != "summary":
            return ""
        area = self.facts.get("complaint_area")
        if area == "咽喉":
            return self._throat_summary()
        if area == "鼻部":
            return self._nose_summary()
        if area == "耳部":
            return self._ear_summary()
        return "我先帮你归纳一下：目前信息还不算完整，建议把最主要的不舒服、持续时间和有没有发热或明显加重先说清楚。"

    def _medical_info_direct_response(self, text: str, hits: list[KnowledgeHit]) -> str:
        area = self.facts.get("complaint_area")
        if _has_any(text, ["检查", "化验", "鼻内镜", "CT", "磁共振"]):
            return self._exam_info_response(text, area)
        if _has_any(text, ["治疗", "用药", "药", "处理", "怎么办"]):
            return self._treatment_info_response(text, area)
        if _has_any(text, ["就医", "复诊", "准备", "注意"]):
            return self._visit_info_response(area)
        source_hint = " ".join(hit.snippet for hit in hits[:2])
        if area == "鼻部" or _has_any(source_hint, ["鼻炎", "鼻窦炎", "鼻息肉"]):
            return self._exam_info_response(text, "鼻部")
        return "这类问题要先把主诉、持续时间和危险信号说清楚，再决定检查和处理方向。线上可以先做健康科普和就医准备，真正的诊断还要结合耳鼻喉科查体和必要检查。"

    def _exam_info_response(self, text: str, area: str | None) -> str:
        if area == "鼻部":
            if _has_any(text, ["鼻窦炎", "慢性鼻窦炎", "鼻息肉"]):
                return (
                    "慢性鼻窦炎反复发作，首先建议做鼻内镜检查，直接看鼻腔和鼻窦开口有没有黏膜水肿、脓性分泌物或鼻息肉。"
                    "如果症状反复、病程长，或者需要评估手术可能性，鼻窦 CT 也很关键，它能看清窦腔炎症范围和解剖结构。"
                    "如果同时有喷嚏、清水涕、鼻痒或季节诱发，再考虑过敏原相关检查。"
                    "带着既往用药、发作频率和检查结果去耳鼻喉科面诊，更容易判断是炎症控制不足还是结构问题。"
                )
            return (
                "鼻部症状常见的第一步检查是鼻内镜，可以看清鼻腔黏膜、鼻甲、分泌物、鼻中隔和鼻息肉等情况。"
                "如果怀疑鼻窦炎、鼻息肉或反复发作，通常还需要鼻窦 CT 来判断炎症范围和解剖结构。"
                "如果表现为反复喷嚏、清水涕、鼻痒，过敏原检查也有参考价值。"
            )
        if area == "咽喉":
            return (
                "咽喉不适反复或持续不缓解，常见第一步是耳鼻喉科查体和喉镜检查，看咽喉黏膜、扁桃体和声带情况。"
                "如果伴发热、明显吞咽痛、声音嘶哑久不恢复或痰血，要更早线下面诊。"
                "检查前把持续时间、疼痛还是干痒、有没有反酸和用嗓情况整理清楚，会更利于判断。"
            )
        if area == "耳部":
            return (
                "耳部不适常见第一步是耳镜检查，看外耳道和鼓膜情况。"
                "如果有耳闷、听力下降或耳鸣，还可能需要听力学检查和声导抗检查。"
                "听力突然下降、明显眩晕、发热或流脓时，要尽快耳鼻喉科处理。"
            )
        return "耳鼻喉科问题一般先根据部位做查体，鼻部看鼻内镜，咽喉部看喉镜，耳部看耳镜；是否需要 CT、过敏原或听力检查，要结合症状持续时间和危险信号判断。"

    def _treatment_info_response(self, text: str, area: str | None) -> str:
        if area == "鼻部":
            return (
                "鼻部反复不适的处理要先区分过敏性鼻炎、鼻窦炎、鼻息肉或鼻腔结构问题。"
                "常见处理方向包括避免诱因、鼻腔冲洗、鼻喷抗炎药物和抗过敏药物类别，但具体用药和疗程需要结合鼻内镜或鼻窦 CT 判断。"
                "如果有黄脓涕、头面部胀痛、嗅觉下降或反复发作，建议尽快耳鼻喉科评估，不要只靠临时吃药压症状。"
            )
        if area == "咽喉":
            return (
                "咽喉不适的处理先看是感染、干燥刺激、用嗓过度、反流还是过敏相关。"
                "一般先减少辛辣烟酒和过度用嗓，保持饮水和空气湿润；是否需要抗感染、抗过敏或反流相关用药，要结合查体判断。"
                "如果发热、吞咽困难、呼吸不顺、痰血或持续一周左右仍不缓解，建议线下耳鼻喉科检查。"
            )
        return "处理方向要先按症状部位和危险信号分层。可以先做基础护理和就医准备，但具体药物、疗程和是否需要进一步检查，建议由耳鼻喉科医生结合查体决定。"

    def _visit_info_response(self, area: str | None) -> str:
        if area == "鼻部":
            return "去耳鼻喉科前，建议准备好症状持续时间、鼻塞流涕性质、喷嚏鼻痒诱因、嗅觉变化、既往用药和既往鼻内镜或鼻窦 CT 结果。若有大量鼻出血、明显头痛、视力变化或持续高热，要提前就医或急诊处理。"
        if area == "咽喉":
            return "去耳鼻喉科前，建议整理咽喉不适持续时间、疼痛或干痒程度、有没有发热吞咽困难、声音嘶哑、反酸、熬夜辛辣和用嗓情况。若呼吸不顺、吞咽困难明显或痰血，要尽快线下处理。"
        return "就医前先整理最主要的不舒服、持续时间、诱因、用药经过和有没有危险信号。耳鼻喉科医生会根据部位决定鼻内镜、喉镜、耳镜、影像或听力检查。"

    def _throat_summary(self) -> str:
        duration = _plain_fact(self.facts.get("duration"), "时间不长")
        quality = _plain_fact(self.facts.get("throat_quality"), "咽喉不适")
        red_flags = self.facts.get("red_flags", "")
        lifestyle = self.facts.get("throat_lifestyle", "")
        medication = self.facts.get("medication", "")
        reassurance = "目前没有听到明显危险信号，"
        if red_flags and not _is_negative(red_flags):
            reassurance = "你提到的情况里有需要警惕的表现，"
        advice = "先多喝水，少吃辛辣，减少熬夜和过度用嗓。"
        if lifestyle and not _is_negative(lifestyle):
            advice = "近期先把饮食、作息和用嗓强度降下来，多喝水观察。"
        if medication and not _is_negative(medication):
            advice += " 如果已经用药但没有缓解，别自行叠加用药。"
        return (
            f"我先归纳一下：你主要是嗓子不舒服，{duration}，表现为{quality}。"
            f"{reassurance}更偏向急性咽喉炎、干燥刺激或上呼吸道感染后咽喉不适这一类问题。{advice}"
            "先不要自行上抗生素；如果疼痛加重、发热、吞咽困难、呼吸不顺、痰里带血，或者已经一周仍不缓解，建议近期耳鼻喉科看一下咽喉情况。"
        )

    def _nose_summary(self) -> str:
        duration = _plain_fact(self.facts.get("duration"), "时间不明确")
        discharge = _plain_fact(self.facts.get("discharge"), "鼻涕性质还不明确")
        trigger = _plain_fact(self.facts.get("trigger"), "诱因不明确")
        return (
            f"我先归纳一下：你主要是鼻部不舒服，持续情况是{duration}，{discharge}，{trigger}。"
            "如果是反复鼻塞、清水涕、喷嚏鼻痒，常见方向包括过敏性鼻炎；如果黄脓涕、头面部胀痛或超过十天不缓解，要考虑鼻窦炎方向。"
            "可以先按过敏性鼻炎或鼻窦炎的临床倾向准备病史资料，再由耳鼻喉科结合鼻内镜、过敏原或鼻窦 CT 确认。"
        )

    def _ear_summary(self) -> str:
        duration = _plain_fact(self.facts.get("duration"), "时间不明确")
        detail = _plain_fact(self.facts.get("ear_detail"), "耳部表现还不完整")
        return (
            f"我先归纳一下：你主要是耳部不适，持续情况是{duration}，表现为{detail}。"
            "如果有听力突然下降、明显眩晕、发热或耳朵流脓，需要尽快耳鼻喉科就诊。"
            "如果症状较轻，可以先避免掏耳和进水，尽快线下检查耳道和鼓膜情况。"
        )

    def _extract_facts(self, text: str) -> None:
        if not _looks_like_correction(text):
            self._record_pending_answer(text)

        self._extract_complaint_area(text)
        if _has_any(text, NOSE_TERMS + THROAT_TERMS + EAR_TERMS + SLEEP_TERMS + ["咳嗽", "不舒服"]):
            self.facts["symptoms"] = _merge_fact(self.facts.get("symptoms"), text)
        if _has_any(text, ["清水", "清鼻涕", "黄鼻涕", "黄脓", "脓涕", "黏", "浓", "稀"]):
            self.facts["discharge"] = _merge_fact(self.facts.get("discharge"), text)
        if DURATION_RE.search(text):
            self.facts["duration"] = _merge_fact(self.facts.get("duration"), text)
        if _has_any(text, ["花粉", "尘螨", "宠物", "猫", "狗", "空调", "冷空气", "冷风", "受凉", "季节", "春天", "秋天", "灰尘", "装修"]):
            self.facts["trigger"] = _merge_fact(self.facts.get("trigger"), text)
        if _has_any(text, ["疼", "痛", "干", "异物感", "痒", "哑", "吞咽", "咳痰", "有痰"]):
            if self.facts.get("complaint_area") == "咽喉" or _has_any(text, THROAT_TERMS):
                self.facts["throat_quality"] = _merge_fact(self.facts.get("throat_quality"), text)
        if _has_any(text, ["熬夜", "吃辣", "辛辣", "喝酒", "抽烟", "用嗓", "说话多", "唱歌", "喊"]):
            self.facts["throat_lifestyle"] = _merge_fact(self.facts.get("throat_lifestyle"), text)
        if _has_any(text, ["耳闷", "耳痛", "听力下降", "听不清", "耳鸣", "流脓"]):
            self.facts["ear_detail"] = _merge_fact(self.facts.get("ear_detail"), text)
        if _has_any(text, ["憋醒", "白天犯困", "暂停", "打鼾", "呼噜"]):
            self.facts["sleep_detail"] = _merge_fact(self.facts.get("sleep_detail"), text)
        if _has_any(text, ["吃过", "用过", "喷", "药", "抗过敏", "氯雷他定", "西替利嗪", "鼻喷", "激素", "洗鼻"]):
            self.facts["medication"] = _merge_fact(self.facts.get("medication"), text)
        if _has_any(text, ["鼻内镜", "CT", "磁共振", "过敏原", "检查", "化验", "手术", "住院"]):
            self.facts["history"] = _merge_fact(self.facts.get("history"), text)
        if _has_any(text, ["发烧", "发热", "出血", "头痛", "视力", "复视", "呼吸困难", "呼吸不顺", "喘不上", "吞咽困难", "流口水"]):
            self.facts["red_flags"] = _merge_fact(self.facts.get("red_flags"), text)

    def _extract_complaint_area(self, text: str) -> None:
        scores = {
            "鼻部": _count_any(text, NOSE_TERMS),
            "咽喉": _count_any(text, THROAT_TERMS),
            "耳部": _count_any(text, EAR_TERMS),
            "睡眠": _count_any(text, SLEEP_TERMS),
        }
        area, score = max(scores.items(), key=lambda item: item[1])
        if score <= 0:
            return
        current = self.facts.get("complaint_area")
        if not current or _looks_like_correction(text) or score > scores.get(current, 0):
            self.facts["complaint_area"] = area

    def _record_pending_answer(self, text: str) -> None:
        slot = self.pending_slot
        if not slot:
            return

        if slot.endswith("_duration"):
            if DURATION_RE.search(text):
                self.facts["duration"] = _merge_fact(self.facts.get("duration"), text)
            return

        if slot == "nose_discharge":
            self.facts["discharge"] = _merge_fact(self.facts.get("discharge"), _answer_value(text, negative="没有明显流涕"))
        elif slot == "nose_trigger":
            self.facts["trigger"] = _merge_fact(self.facts.get("trigger"), _answer_value(text, negative="无明显灰尘、花粉或冷空气诱发"))
        elif slot == "nose_red_flags":
            self.facts["red_flags"] = _merge_fact(self.facts.get("red_flags"), _answer_value(text, negative="否认发热、明显头痛、鼻出血或视力变化"))
        elif slot == "throat_quality":
            self.facts["throat_quality"] = _merge_fact(self.facts.get("throat_quality"), _answer_value(text, negative="未描述明显疼痛、干燥或异物感"))
        elif slot == "throat_red_flags":
            self.facts["red_flags"] = _merge_fact(self.facts.get("red_flags"), _answer_value(text, negative="否认发热、吞咽明显疼痛或呼吸不顺"))
        elif slot == "throat_lifestyle":
            self.facts["throat_lifestyle"] = _merge_fact(self.facts.get("throat_lifestyle"), _answer_value(text, negative="否认熬夜、辛辣饮食或用嗓过多诱因"))
        elif slot == "nosebleed_control":
            self.facts["red_flags"] = _merge_fact(self.facts.get("red_flags"), f"鼻出血止血情况：{text[:120]}")
        elif slot == "ear_detail":
            self.facts["ear_detail"] = _merge_fact(self.facts.get("ear_detail"), _answer_value(text, negative="未描述明显耳闷、耳痛或听力下降"))
        elif slot == "ear_red_flags":
            self.facts["red_flags"] = _merge_fact(self.facts.get("red_flags"), _answer_value(text, negative="否认明显头晕、发热、流脓或听力突然下降"))
        elif slot == "sleep_detail":
            self.facts["sleep_detail"] = _merge_fact(self.facts.get("sleep_detail"), text[:120])
        elif slot == "medication":
            self.facts["medication"] = _merge_fact(self.facts.get("medication"), _answer_value(text, negative="未自行用药"))
        elif slot == "exam_history":
            self.facts["history"] = _merge_fact(self.facts.get("history"), _answer_value(text, negative="未做相关检查"))

    def _facts_summary(self) -> str:
        if not self.facts:
            return "暂未形成完整病史。"
        labels = {
            "complaint_area": "主诉部位",
            "symptoms": "症状",
            "duration": "病程",
            "trigger": "诱因",
            "discharge": "鼻涕性质",
            "throat_quality": "咽喉感受",
            "throat_lifestyle": "生活诱因",
            "ear_detail": "耳部表现",
            "sleep_detail": "睡眠表现",
            "medication": "用药",
            "history": "检查/既往史",
            "red_flags": "危险信号",
        }
        return "；".join(f"{labels.get(key, key)}：{value}" for key, value in self.facts.items())

    def _source_context(self, hits: list[KnowledgeHit]) -> str:
        if not hits:
            return "本轮没有命中额外资料时，按问诊流程继续追问，不要强行下结论，也不要额外追加多个问题。"
        snippets = []
        for hit in hits[:3]:
            snippets.append(f"{hit.source}：{hit.snippet[:220]}")
        return "本轮可参考资料：" + "；".join(snippets) + "。不要向患者报资料来源，不要把资料内容扩写成连续追问。"

    def _build_external_rag(self, user_text: str, stage: str, next_question: str, hits: list[KnowledgeHit]) -> str:
        instructions = (
            f"患者本轮说：{user_text}\n"
            f"当前问诊阶段：{STAGE_LABELS.get(stage, stage)}\n"
            f"已收集病史：{self._facts_summary()}\n"
            f"本轮唯一允许追问的问题：{next_question}\n"
            "回答要求：继续以医生口吻说话。信息不足时，只追问上面这一句话里的一个问题；"
            "最多两句话，普通追问只出现一个问号，问完立刻停下来等患者回答。"
            "不要顺手补问其他信息，也不要把其他主诉轨道的问题带进来。"
            "若信息已经足够，再做阶段性分析，但仍保持简短。不要写成列表，不要报资料来源，不要说正在读取数据库。"
        )
        items = [{"title": "问诊流程与本轮回答要求", "content": instructions}]
        for hit in hits:
            items.append({"title": f"医疗资料：{hit.source}", "content": hit.snippet})
        return _fit_external_rag(items)

    def _build_voice_external_rag(self, user_text: str, stage: str, next_question: str, hits: list[KnowledgeHit]) -> str:
        strategy = self._voice_consultation_strategy(user_text)
        stage_label = STAGE_LABELS.get(stage, stage)
        summary_guidance = self._voice_summary_guidance() if stage == "summary" else ""
        instructions = (
            f"患者本轮说：{user_text}\n"
            f"当前问诊阶段：{stage_label}\n"
            f"已收集病史：{self._facts_summary()}\n"
            f"本轮优先补充信息：{next_question}\n"
            f"本轮问诊策略：{strategy}\n"
            f"{summary_guidance}"
            "回答要求：请根据患者本轮表达和下方资料，用医生口吻做简短、口语化回应。"
            "不要重复询问患者已经明确说出的主诉。"
            "信息不足时，只追问一个当前医学优先级最高的问题，说完等待患者回答。"
            "如果当前阶段是阶段性总结，不要继续补问常规问题，要给出可能方向、依据、日常处理和就医边界。"
            "总结时不要只说线下检查，除非已经出现危险信号；病史相对充分时，可以说目前更符合或更倾向某一类常见诊疗方向，并给出依据和处理重点。"
            "可以提常见用药类别或居家处理原则，但处方药具体剂量、个体化用药调整和疗效保证必须由医生结合检查确认。"
            "不要写成列表，不要报资料来源，不要说正在读取数据库。"
            "如出现持续大量出血、止不住血、明显头痛、视力变化、呼吸困难或意识异常，直接建议尽快线下急诊或耳鼻喉专科处理。"
        )
        items = [{"title": "语音问诊参考与回答边界", "content": instructions}]
        for hit in hits:
            items.append({"title": f"医疗资料：{hit.source}", "content": hit.snippet})
        return _fit_external_rag(items)

    def _voice_consultation_strategy(self, user_text: str) -> str:
        text = _clean_text(user_text)
        if _has_any(text, ["鼻出血", "流鼻血", "鼻血", "鼻子流血"]):
            return (
                "按鼻出血进行安全分层，不要再问患者最主要哪里不舒服。"
                "首要判断现在是否还在流、按压后能否止住、已经流了多久；"
                "随后再按顺序了解出血量、是否反复发作、单侧还是双侧、是否挖鼻或外伤、鼻腔干燥或鼻炎、是否用抗凝药或有高血压，"
                "最后排查明显头痛、视力变化、头晕乏力等危险信号。"
                "本轮优先问止血情况，可以把持续时间合并在同一句里，但不要追加更多问题。"
            )
        if self.facts.get("complaint_area") == "鼻部":
            return (
                "按鼻部症状问诊推进。优先确认持续时间和单侧/双侧，再追问鼻塞、流涕性质、喷嚏鼻痒、嗅觉变化、诱因、睡眠影响，"
                "之后再问用药、鼻内镜/过敏原/鼻窦CT等检查史，并排查发热、明显头痛、鼻出血或视力变化。"
                "本轮只问当前最缺的一个信息，不要一次问成症状清单。"
            )
        if self.facts.get("complaint_area") == "咽喉":
            return (
                "按咽喉不适问诊推进。先确认持续时间，再区分疼、干、异物感、声音嘶哑或吞咽痛，随后了解发热、呼吸不顺、熬夜辛辣用嗓和用药情况。"
                "本轮只问当前最缺的一个信息。"
            )
        if self.facts.get("complaint_area") == "耳部":
            return (
                "按耳部症状问诊推进。先确认持续时间，再区分耳闷、耳痛、耳鸣、听力下降，随后排查眩晕、发热、流脓或听力突然下降。"
                "本轮只问当前最缺的一个信息。"
            )
        return (
            "先根据患者话语识别主诉属于鼻部、咽喉、耳部还是睡眠相关；"
            "若主诉已经明确，不要再笼统追问主诉，直接进入该主诉的持续时间、严重程度和危险信号分层。"
        )

    def _voice_summary_guidance(self) -> str:
        area = self.facts.get("complaint_area")
        if area == "咽喉":
            return (
                "阶段性总结参考：先复述已知病史；再说明可能方向可偏向急性咽喉炎、干燥刺激或上呼吸道感染后咽喉不适，"
                "依据是咽痛咽干、病程、是否发热和是否呼吸不顺等已收集信息；"
                "再给出多饮水、减少辛辣烟酒和过度用嗓、保持空气湿润、不要自行使用抗生素等日常处理；"
                "最后说明如果疼痛加重、发热、吞咽困难、呼吸不顺、痰血，或一周左右仍无改善，应近期耳鼻喉科面诊。"
            )
        if area == "鼻部":
            return (
                "阶段性总结参考：先复述鼻部主诉、病程、鼻涕性质、诱因、危险信号和用药情况；"
                "再区分可能方向，比如清水涕喷嚏鼻痒偏过敏性鼻炎，黄脓涕伴头面部痛或超过十天不缓解偏鼻窦炎方向，"
                "反复鼻出血要看出血量、止血情况和诱因；再给出避免诱因、鼻腔保湿或冲洗、不要抠鼻和不要自行叠加用药等建议；"
                "最后说明哪些情况需要尽快面诊或急诊。"
            )
        if area == "耳部":
            return (
                "阶段性总结参考：先复述耳部不适、病程和耳闷耳痛耳鸣听力变化；"
                "再说明可能方向包括外耳道、鼓膜或咽鼓管相关问题，需要结合耳镜判断；"
                "轻症先避免掏耳和进水，若听力突然下降、明显眩晕、发热或流脓，应尽快耳鼻喉科处理。"
            )
        return "阶段性总结参考：用已收集病史说明可能方向、目前没有或存在的危险信号、日常处理和就医边界。"


def _fit_external_rag(items: list[dict[str, str]]) -> str:
    packed = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    if len(packed) <= MAX_EXTERNAL_RAG_CHARS:
        return packed

    trimmed: list[dict[str, str]] = []
    budget = MAX_EXTERNAL_RAG_CHARS - 64
    for item in items:
        title = item["title"][:80]
        content = item["content"]
        remaining = budget - sum(len(x["title"]) + len(x["content"]) + 20 for x in trimmed)
        if remaining <= 80:
            break
        trimmed.append({"title": title, "content": content[:remaining]})
    return json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"))[:MAX_EXTERNAL_RAG_CHARS]


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _has_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _count_any(text: str, needles: list[str]) -> int:
    return sum(1 for needle in needles if needle in text)


def _looks_like_correction(text: str) -> bool:
    return _has_any(text, ["我说的是", "不是", "不对", "搞错", "听错"])


def _looks_like_medical_info_question(text: str) -> bool:
    return _has_any(text, ["？", "?", "什么", "怎么", "如何", "一般", "需要", "要不要", "能不能"]) and _has_any(
        text,
        ["检查", "治疗", "用药", "药", "手术", "处理", "怎么办", "就医", "复诊", "注意", "准备"],
    )


def _is_negative(text: str) -> bool:
    if re.search(r"(^|[，,。\s])有([，,。\s]|$)", text) and _has_any(text, ["没有", "没"]):
        return False
    compact = re.sub(r"[，。,.！!？?\s]", "", text)
    if _has_any(compact, ["有没有", "有没"]):
        return False
    return compact in {"不", "不会", "没有", "没", "无", "不是", "否", "未"} or _has_any(text, ["没有", "没用", "没吃", "不会", "不是", "无明显", "否认", "未自行"])


def _answer_value(text: str, *, negative: str) -> str:
    cleaned = text[:120]
    if _is_negative(text):
        return negative
    return cleaned


def _plain_fact(value: str | None, fallback: str) -> str:
    cleaned = re.sub(r"[，。,.！!？?\s]+$", "", value or "").strip()
    return cleaned or fallback


def _merge_fact(old: str | None, new: str) -> str:
    if not old:
        return new[:120]
    if new in old:
        return old
    merged = f"{old}；{new}"
    return merged[-180:]
