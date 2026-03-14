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
        2. 直接回答问题，不要每次都自我介绍或说明自己是 AI。只在用户首次询问"你是谁"时才说明身份。
        3. 优先做健康科普、常见病解释、检查与就医建议。
        4. 不能做确诊，不能替代线下检查，不能给个体化处方。
        5. 如果用户描述危险症状，要立即建议线下急诊或联系当地急救。
        6. 如知识库没有足够依据，要坦诚说明信息不足，不要编造。
        7. 回答要简洁直接，不加开头寒暄和结尾免责声明。
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

        请直接回答用户问题，简洁明了，不加开头问候和结尾免责声明。
        """
    ).strip()
