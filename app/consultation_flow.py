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
        hits = search_knowledge(normalized, top_k=5)
        external_rag = self._build_external_rag(normalized, stage, hits)
        dynamic_role = self._dynamic_system_role(stage, hits)
        return ConsultationTurn(
            user_text=normalized,
            stage=stage,
            stage_label=STAGE_LABELS.get(stage, stage),
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
            "问诊阶段每次只问一到两个关键问题，围绕主诉、持续时间、诱因、伴随症状、既往检查、用药经过和危险信号逐步收集。"
            "信息不足时不要急着下结论，至少经过两到三轮追问后再做阶段性分析。"
            "回答要依据系统随后提供的外部资料和已收集病史，不要编造检查结果、处方剂量或确定诊断。"
            "遇到呼吸困难、意识异常、持续高热、剧烈头痛、反复大量出血、明显视力或神经症状时，直接建议尽快线下急诊或专科就医。"
            "不要使用列表、编号、加粗或书面报告格式，保持口语化。"
        )

    def _dynamic_system_role(self, stage: str, hits: list[KnowledgeHit]) -> str:
        stage_rule = {
            "chief": "当前任务是确认患者最主要的不舒服是什么，并问清楚最困扰他的一个症状。",
            "symptoms": "当前任务是细化症状组合，追问鼻塞、流涕、喷嚏、鼻痒、嗅觉、咽喉、耳闷、睡眠等相关表现。",
            "duration_trigger": "当前任务是追问病程、发作规律、季节性、环境暴露、冷热刺激、尘螨花粉宠物等诱因。",
            "history": "当前任务是追问既往检查、过敏史、用药经过、疗效、基础疾病和近期手术治疗情况。",
            "red_flag": "当前任务是先判断有没有危险信号，必要时直接建议线下急诊或尽快专科就医。",
            "summary": "当前任务是基于已收集信息做阶段性分析，同时给出下一步就医准备、检查方向和日常注意事项。",
        }.get(stage, "当前任务是继续完成耳鼻咽喉科问诊。")
        facts = self._facts_summary()
        source_context = self._source_context(hits)
        return f"{self._base_system_role()} 已收集信息：{facts} {stage_rule} {source_context}"

    def _speaking_style(self) -> str:
        traits = "、".join(self.profile.get("style_traits", []))
        if not traits:
            traits = "先安抚情绪，再解释问题；用词朴素，不夸张；习惯先说需要补充哪些信息"
        return f"{traits}。语速平稳，回答简洁但有信息量。"

    def _current_stage(self, text: str) -> str:
        if _has_any(text, ["呼吸困难", "喘不上", "意识", "昏迷", "大量出血", "止不住血", "视力下降", "复视", "剧烈头痛"]):
            return "red_flag"
        if self.turn_count <= 1:
            return "symptoms"
        missing_duration = "duration" not in self.facts
        missing_trigger = "trigger" not in self.facts
        missing_history = "history" not in self.facts and "medication" not in self.facts
        if missing_duration or missing_trigger:
            return "duration_trigger"
        if missing_history:
            return "history"
        if self.turn_count < 3:
            return "red_flag"
        return "summary"

    def _extract_facts(self, text: str) -> None:
        if _has_any(text, ["鼻塞", "流鼻涕", "流涕", "喷嚏", "打喷嚏", "鼻痒", "嗅觉", "耳闷", "咳嗽", "咽痛", "打鼾"]):
            self.facts["symptoms"] = _merge_fact(self.facts.get("symptoms"), text)
        if re.search(r"(\d+\s*[天周月年]|一周|两周|半个月|一个月|几天|几年|长期|反复|最近|从小)", text):
            self.facts["duration"] = _merge_fact(self.facts.get("duration"), text)
        if _has_any(text, ["花粉", "尘螨", "宠物", "猫", "狗", "空调", "冷空气", "季节", "春天", "秋天", "灰尘", "装修"]):
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
            "medication": "用药",
            "history": "检查/既往史",
            "red_flags": "危险信号",
        }
        return "；".join(f"{labels.get(key, key)}：{value}" for key, value in self.facts.items())

    def _source_context(self, hits: list[KnowledgeHit]) -> str:
        if not hits:
            return "本轮没有命中额外资料时，按问诊流程继续追问，不要强行下结论。"
        snippets = []
        for hit in hits[:3]:
            snippets.append(f"{hit.source}：{hit.snippet[:220]}")
        return "本轮可参考资料：" + "；".join(snippets) + "。不要向患者报资料来源。"

    def _build_external_rag(self, user_text: str, stage: str, hits: list[KnowledgeHit]) -> str:
        instructions = (
            f"患者本轮说：{user_text}\n"
            f"当前问诊阶段：{STAGE_LABELS.get(stage, stage)}\n"
            f"已收集病史：{self._facts_summary()}\n"
            "回答要求：继续以医生口吻说话。若信息不足，先追问一到两个最关键问题；"
            "若信息已经足够，再做阶段性分析。不要写成列表，不要报资料来源，不要说正在读取数据库。"
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
