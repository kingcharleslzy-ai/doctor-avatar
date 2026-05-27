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

    print("consultation_flow ok")


if __name__ == "__main__":
    main()
