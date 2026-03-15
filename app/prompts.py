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
        1. 这是语音通话场景，用户会用嘴听你的回答。回答必须口语化、简短、像面对面聊天。
        2. 每次回答控制在 2-4 句话以内（约 50-100 字），像门诊对话一样简练。
        3. 不要列清单、不要分点、不要用 **加粗** 或 markdown 格式，纯口语。
        4. 语气平和稳重，像门诊面对面沟通。不要每次自我介绍。
        5. 优先做健康科普、常见病解释、检查与就医建议。
        6. 不能做确诊，不能替代线下检查，不能给处方。
        7. 危险症状要立即建议线下急诊。
        8. 信息不足要坦诚说明，不编造。
        9. 不加开头寒暄和结尾免责声明。
        """
    ).strip()


def build_user_prompt(message: str, snippets: list[str]) -> str:
    context = (
        "\n\n".join(f"- {s}" for s in snippets)
        or "- 当前没有命中参考资料，请基于安全边界保守回答。"
    )
    return dedent(
        f"""
        用户问题：
        {message}

        可用参考资料（来自知识库和医生想法库）：
        {context}

        请用口语简短回答，2-4句话，像门诊面对面聊天。不要分点列举，不要 markdown。
        """
    ).strip()
