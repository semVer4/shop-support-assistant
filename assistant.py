"""The model writes the answer; deterministic checks enforce critical rules."""
from dataclasses import dataclass
from pathlib import Path
import json
from guards import check_answer, context

ROOT = Path(__file__).resolve().parent
KB = json.loads((ROOT / "knowledge_base.json").read_text(encoding="utf-8"))
RULES = {rule["id"]: rule for rule in KB["rules"]}
SAFE_REPLY = "Не могу подтвердить корректный ответ по регламенту. Уточните, пожалуйста, этот вопрос у сотрудника магазина."
UNAVAILABLE_REPLY = "Сейчас не получается обратиться к нейросети. Попробуйте, пожалуйста, немного позже."


def fill_prompt(name):
    return (ROOT / name).read_text(encoding="utf-8").replace("{{KNOWLEDGE_BASE}}", "\n".join(f"- [{r['id']}] {r['text']}" for r in KB["rules"]))


def system_prompt():
    return fill_prompt("system_prompt.txt")


def request_context(message):
    value = context(message)
    return json.dumps({
        "статусы_заказов_не_подключены": True,
        "вопрос_о_конкретном_заказе": value["order"],
        "прошло_дней_в_вопросе": sorted(value["days"]),
        "срок_обычного_возврата_дней": RULES["return"]["days"],
        "срок_обычного_возврата_истек": bool(value["return"] and value["days"] and max(value["days"]) > RULES["return"]["days"] and not value["defect"]),
        "в_вопросе_упомянут_брак": value["defect"],
        "скидки_запрещены": True,
        "есть_запрос_отсутствующих_сведений": value["unknown"],
        "другая_модель_товара": value["other_product"],
    }, ensure_ascii=False)


@dataclass
class Reply:
    answer: str
    sources: list[str]
    mode: str
    needs_human: bool
    llm: dict | None = None
    answer_origin: str = "safety_fallback"

    def as_dict(self):
        return self.__dict__.copy()


def answer_question(message, model=None):
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Напишите вопрос")
    if len(message) > 2000:
        raise ValueError("Вопрос должен быть не длиннее 2000 символов")
    if model is None:
        return Reply(UNAVAILABLE_REPLY, [], "model-unavailable", True, answer_origin="unavailable")
    try:
        generated = model.generate(message, system_prompt() + "\n\nПроверенные сведения приложения для этого запроса:\n" + request_context(message))
    except Exception:
        return Reply(UNAVAILABLE_REPLY, [], "model-unavailable", True, answer_origin="unavailable")
    draft = generated.value
    trace = {**generated.trace, "generated_answer": draft.get("answer") if isinstance(draft, dict) else None}
    errors = check_answer(message, draft, RULES)
    trace["code_violations"] = errors
    if errors:
        return Reply(SAFE_REPLY, [], "safety-fallback", True, trace)
    # The accepted text is the actual model output, not a template or rewrite.
    return Reply(draft["answer"], draft["source_ids"], "llm+policy", draft["needs_human"], trace, "model")
