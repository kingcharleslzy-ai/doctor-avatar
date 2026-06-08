from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.consultation_flow import ConsultationOrchestrator


def _turns(inputs: list[str]) -> list[str]:
    orchestrator = ConsultationOrchestrator({"name": "李勇", "title": "医生", "specialty": "耳鼻咽喉科"})
    return [orchestrator.prepare_turn(text).direct_response for text in inputs]


def _voice_turns(inputs: list[str]):
    orchestrator = ConsultationOrchestrator({"name": "李勇", "title": "医生", "specialty": "耳鼻咽喉科"})
    return [orchestrator.prepare_voice_rag_turn(text) for text in inputs]


def main() -> None:
    throat = _turns([
        "我嗓子不舒服。",
        "持续两天了。",
        "干。",
        "不会。",
        "不会。",
        "没有。",
    ])
    assert throat[0] == "嗓子不舒服持续几天了？"
    assert throat[1] == "主要是疼、干，还是有异物感？"
    assert throat[2] == "有没有发热、吞咽明显疼痛或呼吸不顺？"
    assert throat[3] == "最近有熬夜、吃辣，或者用嗓比较多吗？"
    assert throat[4] == "这次自己用过什么药或含片吗？"
    assert "嗓子不舒服" in throat[5]
    assert "鼻塞" not in "".join(throat)
    assert "流涕" not in "".join(throat)
    assert all(text.count("？") <= 1 for text in throat[:5])

    correction = _turns(["我我嗓子不舒服。", "我说的是嗓子不舒服。"])
    assert correction == ["嗓子不舒服持续几天了？", "嗓子不舒服持续几天了？"]

    nose = _turns(["我鼻塞流鼻涕。", "三天了。", "清水鼻涕。", "不会。"])
    assert nose[0] == "鼻子不舒服持续几天了？"
    assert nose[1] == "鼻涕是清水样，还是黄脓鼻涕？"
    assert nose[2] == "接触灰尘、花粉或冷空气后，会明显加重吗？"
    assert nose[3] == "有没有发热、明显头痛、鼻出血或视力变化？"

    info_question = ConsultationOrchestrator({"name": "李勇", "title": "医生", "specialty": "耳鼻咽喉科"}).prepare_turn(
        "慢性鼻窦炎反复发作，一般要先做什么检查？"
    )
    assert info_question.stage == "summary"
    assert "鼻内镜检查" in info_question.direct_response
    assert "鼻窦 CT" in info_question.direct_response
    assert "？" not in info_question.direct_response
    assert "主诉部位：鼻部" in info_question.external_rag
    assert "不要追问，直接回答患者本轮关于检查" in info_question.update_config["dialog"]["system_role"]
    assert "你现在最主要的不舒服是什么" not in info_question.update_config["dialog"]["system_role"]

    voice_throat = _voice_turns([
        "我的嗓子不舒服。",
        "一直持续一星期了。",
        "又疼又干。",
        "没有。",
        "都没有。",
        "没有吃。",
    ])
    assert voice_throat[0].next_question == "嗓子不舒服持续几天了？"
    assert voice_throat[1].next_question == "主要是疼、干，还是有异物感？"
    assert voice_throat[2].next_question == "有没有发热、吞咽明显疼痛或呼吸不顺？"
    assert voice_throat[3].next_question == "最近有熬夜、吃辣，或者用嗓比较多吗？"
    assert voice_throat[4].next_question == "这次自己用过什么药或含片吗？"
    assert voice_throat[5].stage == "summary"
    assert "一星期" in voice_throat[5].external_rag
    assert "否认发热、吞咽明显疼痛或呼吸不顺" in voice_throat[5].external_rag
    assert "阶段性总结参考" in voice_throat[5].external_rag
    assert "不要只说线下检查" in voice_throat[5].external_rag
    assert "更符合或更倾向" in voice_throat[5].external_rag
    assert "不要给确定诊断、处方剂量或保证性结论" not in voice_throat[5].external_rag

    voice_nosebleed = _voice_turns(["我鼻子流血。"])
    assert voice_nosebleed[0].next_question == "这次流鼻血现在按压能止住吗？"
    assert "本轮优先补充信息：这次流鼻血现在按压能止住吗？" in voice_nosebleed[0].external_rag
    assert "本轮优先补充信息：鼻子不舒服持续几天了？" not in voice_nosebleed[0].external_rag

    print("consultation_flow ok")


if __name__ == "__main__":
    main()
