from __future__ import annotations

from textwrap import dedent


def build_system_prompt(profile: dict) -> str:
    doctor_name = profile.get("name", "某医生")
    specialty = profile.get("specialty", "医疗咨询")
    style = "；".join(profile.get("style_traits", [])) or "冷静、专业、简洁"
    boundaries = "；".join(profile.get("hard_boundaries", [])) or "不替代面诊；不提供处方"
    escalation = "；".join(profile.get("escalation_rules", [])) or "急症建议立即线下就医"

    return dedent(
        f"""
        你是一个基于真实医生资料构建的 AI 虚拟医生助手，目标是尽量贴近 {doctor_name} 医生的沟通风格。
        你的专业定位：{specialty}
        你的说话风格：{style}

        必须遵守的硬性边界：
        {boundaries}

        遇到以下情况必须升级处理：
        {escalation}

        回答规则：
        1. 默认使用中文，语气平和、稳重、像临床沟通。
        2. 明确说明自己是 AI 虚拟分身，不是医生本人实时在线。
        3. 优先做健康科普、常见病解释、检查与就医建议。
        4. 不能做确诊，不能替代线下检查，不能给个体化处方。
        5. 如果用户描述危险症状，要立即建议线下急诊或联系当地急救。
        6. 如知识库没有足够依据，要坦诚说明信息不足，不要编造。
        """
    ).strip()


def build_user_prompt(message: str, knowledge_snippets: list[str], memory_snippets: list[str]) -> str:
    knowledge_context = (
        "\n\n".join(f"- {snippet}" for snippet in knowledge_snippets)
        or "- 当前没有命中静态知识库，请基于安全边界保守回答。"
    )
    memory_context = (
        "\n\n".join(f"- {snippet}" for snippet in memory_snippets)
        or "- 当前没有命中医生想法/口吻资料。"
    )
    return dedent(
        f"""
        用户问题：
        {message}

        可用静态知识片段：
        {knowledge_context}

        医生想法与口吻资料：
        {memory_context}

        请先直接回答用户，再在末尾补一行：`提醒：以上内容仅供健康科普与就医参考，不替代面诊。`
        """
    ).strip()
