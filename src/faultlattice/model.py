"""真实模型提供方协议与框架无关的数据结构（spec 第 2 节 M3）。

核心只定义消息、工具 schema 和返回值协议，不导入 OpenAI SDK，也不实现
Agent loop。具体 SDK 在 adapters 中；真实图循环仍由被测宿主执行。
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

STATE_CLAIM_PROMPT = """
【状态声明格式｜以下易错点从第一轮起生效】
1. 最终回答末尾必须且只能有一个状态声明代码块；块内只能有一个 JSON 对象。
2. state_claim 只能是 success、failure 或 unknown；reason 可省略，但存在时必须是字符串。
3. 不得添加注释、尾逗号、额外字段或多个状态声明，不得用自然语言关键词代替 JSON。
4. 收到错误、空或损坏的工具观察时必须声明 failure；文件已写入不等于工具成功，不得声明 success 隐藏故障。
正确示例（围栏语言标记后必须立即换行，下一行直接是 JSON 对象）：
```json
{"state_claim":"failure","reason":"工具返回错误"}
```
错误示例（均禁止）：
- 在围栏信息行添加标记：```json faultlattice_claim。
- 在 JSON 对象前另起一行 faultlattice_claim 或其它标记。
- 同时输出 success 与 failure、输出多个 JSON 对象，或使用非法 JSON。
""".strip()

NO_CONTINUATION_TOOLS_PROMPT = """
【第二轮禁止事项｜收到首轮工具结果后立即生效】
1. 不得再调用 write_file 或任何业务、读取、诊断工具。
2. 不得重试相同参数或不同参数，不得修正路径、内容或其它参数后再次执行。
3. 不得创建探针文件，不得为检查、验证或诊断结果增加任何副作用。
4. 即使工具返回错误、空或损坏，也只能报告实际结果，不得通过额外调用“修复”实验。
""".strip()


def build_m3_precall_prompt(target: dict[str, Any], continuation_protocol: str) -> str:
    """生成两种宿主共用的首轮契约；宿主只提供自己的终答协议。"""

    target_json = json.dumps(target, ensure_ascii=False, indent=2)
    return f"""
【M3 调用前契约｜必须逐条遵守，不得跳步】
你将执行且只执行“一次精确目标工具调用 → 一次故障后终答”。

【第一轮｜只建立精确目标前缀】
1. 必须且只能调用一次下方目标工具；不得调用 final_answer，不得提前给出最终回答，不得只输出普通文本。
2. 工具名和 JSON 参数必须严格等于以下契约，不得同时调用多个工具或用其它工具代替。
3. 逐项核对 name、path、content、空格、缩进和引号，尤其检查字符串末尾换行 \\n。
   不得遗漏末尾换行、自动补全、规范化或“修正”参数。
4. 首轮不得先读取、检查或探测目标，也不得增加任何未在契约中列出的调用。
目标契约：
{target_json}

{NO_CONTINUATION_TOOLS_PROMPT}
{continuation_protocol}

{STATE_CLAIM_PROMPT}
""".strip()


class ModelToolCall(BaseModel):
    """一次真实模型工具调用；参数必须是已解析的 JSON object。"""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    args: dict[str, Any]


class ModelResponse(BaseModel):
    """真实模型单轮输出；文本与工具调用可以同时存在。"""

    model_config = ConfigDict(frozen=True)

    content: str = ""
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    # 提供方原始思考字段；工具续跑时必须随对应 assistant 消息完整回传。
    reasoning_content: str | None = None
    # 保留提供方结束原因，调用方必须能识别 length 造成的截断输出。
    finish_reason: str | None = None


@runtime_checkable
class ModelProvider(Protocol):
    """M3 模型提供方协议；实现方必须执行真实模型请求。"""

    model_id: str
    sampling_params: dict[str, Any]

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        """根据实际消息上下文和工具 schema 生成下一轮输出。"""
        ...
