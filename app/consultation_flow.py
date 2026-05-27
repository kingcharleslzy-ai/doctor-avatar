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


@dataclass
class ConsultationTurn:
    user_text: str
    stage: str
    stage_label: str
    next_question: str
    external_rag: str
    update_config: dict
    hit_sources: list[str]


@dataclass
class ConsultationOrchestrator:
    profile: dict
    turn_count: int = 0
    facts: dict[str, str] = field(default_factory=dict)
    user_history: list[str] = field(default_factory=list)

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

        stage = self._current_stage(normalized)
        next_question = self._next_question(stage)
        hits = search_knowledge(normalized, top_k=5)
        external_rag = self._build_external_rag(normalized, stage, next_question, hits)
        dynamic_role = self._dynamic_system_role(stage, next_question, hits)
        return ConsultationTurn(
            user_text=normalized,
            stage=stage,
            stage_label=STAGE_LABELS.get(stage, stage),
            next_question=next_question,
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
            "围绕主诉、持续时间、鼻涕性质、诱因、伴随症状、既往检查、用药经过和危险信号逐步收集。"
            "信息不足时不要急着下结论，至少经过两到三轮追问后再做阶段性分析。"
            "回答要依据系统随后提供的外部资料和已收集病史，不要编造检查结果、处方剂量或确定诊断。"
            "遇到呼吸困难、意识异常、持续高热、剧烈头痛、反复大量出血、明显视力或神经症状时，直接建议尽快线下急诊或专科就医。"
            "不要使用列表、编号、加粗或书面报告格式，保持口语化；普通追问尽量只出现一个问号。"
        )

    def _dynamic_system_role(self, stage: str, next_question: str, hits: list[KnowledgeHit]) -> str:
        stage_rule = {
            "chief": "当前任务是确认主诉，只问患者最主要的不舒服。",
            "symptoms": "当前任务是细化一个症状点，不展开成症状清单。",
            "duration_trigger": "当前任务是在病程和诱因里只补一个缺口。",
            "history": "当前任务是在用药、检查或既往史里只补一个缺口。",
            "red_flag": "当前任务是先排查一个最重要的危险信号组合；如患者有明显危险信号，直接建议线下急诊或尽快专科就医。",
            "summary": "当前任务是做简短阶段性分析，必要时只给一个下一步建议。",
        }.get(stage, "当前任务是继续完成耳鼻咽喉科问诊。")
        facts = self._facts_summary()
        source_context = self._source_context(hits)
        return (
            f"{self._base_system_role()} 已收集信息：{facts} {stage_rule} "
            f"本轮优先话术：{next_question} 必须围绕这一个点说，不能额外追加第二串问题。"
            f"{source_context}"
        )

    def _speaking_style(self) -> str:
        traits = "、".join(self.profile.get("style_traits", []))
        if not traits:
            traits = "先安抚情绪，再解释问题；用词朴素，不夸张；习惯先说需要补充哪一个信息"
        return f"{traits}。语速平稳，回答简短；问诊追问每轮只问一个问题。"

    def _current_stage(self, text: str) -> str:
        if _has_any(text, ["呼吸困难", "喘不上", "意识", "昏迷", "大量出血", "止不住血", "视力下降", "复视", "剧烈头痛"]):
            return "red_flag"
        if self.turn_count <= 1:
            return "symptoms"
        missing_discharge = "discharge" not in self.facts and _has_any(self.facts.get("symptoms", ""), ["鼻塞", "流鼻涕", "流涕"])
        missing_duration = "duration" not in self.facts
        missing_trigger = "trigger" not in self.facts
        missing_history = "history" not in self.facts and "medication" not in self.facts
        if missing_duration:
            return "duration_trigger"
        if missing_discharge:
            return "symptoms"
        if missing_trigger:
            return "duration_trigger"
        if missing_history:
            return "history"
        if self.turn_count < 3:
            return "red_flag"
        return "summary"

    def _next_question(self, stage: str) -> str:
        symptoms = self.facts.get("symptoms", "")
        if stage == "chief":
            return "你现在最主要的不舒服是什么？"
        if stage == "symptoms":
            if "duration" not in self.facts and symptoms:
                return "先说一个最关键的：这次症状持续几天了？"
            if "discharge" not in self.facts and _has_any(symptoms, ["流鼻涕", "流涕", "鼻塞"]):
                return "鼻涕是清水样，还是黄脓鼻涕？"
            return "现在最困扰你的是鼻塞、流涕，还是打喷嚏鼻痒？"
        if stage == "duration_trigger":
            if "duration" not in self.facts:
                return "这次症状持续几天了？"
            return "接触灰尘、花粉或冷空气后，会明显加重吗？"
        if stage == "history":
            if "medication" not in self.facts:
                return "这次用过鼻喷、抗过敏药或洗鼻吗？"
            return "之前做过鼻内镜、过敏原或鼻窦 CT 检查吗？"
        if stage == "red_flag":
            return "有没有发热、明显头痛、鼻出血或视力变化？"
        if stage == "summary":
            return "我先帮你把目前情况简单归纳一下。"
        return "我再补问一个关键信息。"

    def _extract_facts(self, text: str) -> None:
        if _has_any(text, ["鼻塞", "流鼻涕", "流涕", "喷嚏", "打喷嚏", "鼻痒", "嗅觉", "耳闷", "咳嗽", "咽痛", "打鼾"]):
            self.facts["symptoms"] = _merge_fact(self.facts.get("symptoms"), text)
        if _has_any(text, ["清水", "清鼻涕", "黄鼻涕", "黄脓", "脓涕", "黏", "浓", "稀", "鼻涕"]):
            self.facts["discharge"] = _merge_fact(self.facts.get("discharge"), text)
        if re.search(r"(\d+\s*[天周月年]|[一二两三四五六七八九十半]+[天周月年]|几天|几年|长期|反复|从小)", text):
            self.facts["duration"] = _merge_fact(self.facts.get("duration"), text)
        if _has_any(text, ["花粉", "尘螨", "宠物", "猫", "狗", "空调", "冷空气", "冷风", "受凉", "季节", "春天", "秋天", "灰尘", "装修"]):
            self.facts["trigger"] = _merge_fact(self.facts.get("trigger"), text)
        if _has_any(text, ["吃过", "用过", "喷", "药", "抗过敏", "氯雷他定", "西替利嗪", "鼻喷", "激素", "洗鼻"]):
            self.facts["medication"] = _merge_fact(self.facts.get("medication"), text)
        if _has_any(text, ["鼻内镜", "CT", "磁共振", "过敏原", "检查", "化验", "手术", "住院"]):
            self.facts["history"] = _merge_fact(self.facts.get("history"), text)
        if _has_any(text, ["发烧", "出血", "头痛", "视力", "复视", "呼吸困难", "喘不上"]):
            self.facts["red_flags"] = _merge_fact(self.facts.get("red_flags"), text)

    def _facts_summary(self) -> str:
        if not self.facts:
            return "暂未形成完整病史。"
        labels = {
            "symptoms": "症状",
            "duration": "病程",
            "trigger": "诱因",
            "discharge": "鼻涕性质",
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
            f"本轮优先话术：{next_question}\n"
            "回答要求：继续以医生口吻说话。信息不足时，只追问本轮优先话术里的一个问题；"
            "最多两句话，普通追问只出现一个问号，问完立刻停下来等患者回答。"
            "若信息已经足够，再做阶段性分析，但仍保持简短。不要写成列表，不要报资料来源，不要说正在读取数据库。"
        )
        items = [{"title": "问诊流程与本轮回答要求", "content": instructions}]
        for hit in hits:
            items.append({"title": f"医疗资料：{hit.source}", "content": hit.snippet})
        return _fit_external_rag(items)


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


def _merge_fact(old: str | None, new: str) -> str:
    if not old:
        return new[:120]
    if new in old:
        return old
    merged = f"{old}；{new}"
    return merged[-180:]
