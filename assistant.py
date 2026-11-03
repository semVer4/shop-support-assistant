"""Small FAQ assistant: an optional model selects topics; only policy supplies answers."""
from dataclasses import dataclass
from pathlib import Path
import json
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
KB = json.loads((ROOT / "knowledge_base.json").read_text(encoding="utf-8"))
RULES = {rule["id"]: rule for rule in KB["rules"]}
TOPICS = {"product", "delivery", "return", "defect", "discount", "greeting", "unknown"}


def system_prompt():
    template = (ROOT / "system_prompt.txt").read_text(encoding="utf-8")
    return template.replace("{{KNOWLEDGE_BASE}}", "\n".join(f"- [{r['id']}] {r['text']}" for r in KB["rules"]))


def normalize(text):
    return unicodedata.normalize("NFKC", text).lower().replace("ё", "е").replace("х1", "x1")


def elapsed_days(text):
    matches = re.findall(r"\b(\d{1,4})\s*(?:[-–]?\s*(?:й|ый|ой|го|ом|му)\s*)?(?:день|дня|дней|дню|дне)\b", text)
    days = {int(number) for number in matches}
    for word, number in (("шестнадцат", 16), ("пятнадцат", 15), ("четырнадцат", 14), ("тринадцат", 13)):
        if re.search(word + r"\w*\s+(?:день|дня|дней|дню|дне)", text):
            days.add(number)
    if "две недели" in text:
        days.add(14)
    if "три недели" in text:
        days.add(21)
    return days


def parse_question(text):
    topics = set()
    if re.search(r"скид|промокод|дисконт|дешевле|discount", text):
        topics.add("discount")
    if re.search(r"достав|курьер|привез|привоз|прие[дз]|delivery", text):
        topics.add("delivery")
    if re.search(r"верну|возврат|верне|вскры|распак|упаков|зачисл", text):
        topics.add("return")
    no_defect = re.sub(r"без\s+брака|без\s+дефектов|брака\s+нет|дефектов\s+нет|не\s+бракован\w*|\bисправн\w*", "", text)
    if re.search(r"брак|дефект|не\s*работа|неисправ|сломан|поломан", no_defect):
        topics.add("defect")
    if re.search(r"цен[ауы]|стоит|стоимость|почем|налич|купить|есть\s+(?:ли\s+)?(?:у\s+вас\s+)?(?:x1|наушник)|x1", text):
        topics.add("product")
    # Individual order data must never be replaced by the general delivery policy.
    order = bool(re.search(r"заказ|трек(?:инг)?|оплатил|списал|моя\s+посылк|мой\s+возврат", text))
    order_match = re.search(r"заказ\w*\s*(?:№|номер|#)?\s*(\d{1,12})\b", text)
    unknown = bool(re.search(r"цвет|сини|черн|белы|красн|серые|розов|зелен|гарант|адрес|город|минск|москв|совместим|bluetooth|блют|заряд|батаре|срок\s+экспертиз|сколько\s+длится\s+экспертиз|закон|юрист|стать[яеи]|бесплатн|стоимость\s+достав|сколько\s+стоит\s+достав|когда\s+именно|дат[аыу]\s+(?:выплат|зачисл)|(?:x|х)[2-9]\b", text))
    if re.search(r"(?:x|х)[2-9]\b", text):
        topics.discard("product")
    if re.search(r"стоимость\s+достав|сколько\s+стоит\s+достав", text) and "x1" not in text:
        topics.discard("product")
    if not topics and re.fullmatch(r"\s*(?:здравствуйте|привет|добрый\s+(?:день|вечер)|доброе\s+утро)[!.\s]*", text):
        topics.add("greeting")
    return topics, order, order_match.group(1) if order_match else None, unknown


def validate_topics(value):
    if not isinstance(value, dict) or set(value) != {"topics"}:
        raise ValueError("Invalid classifier response")
    items = value["topics"]
    if not isinstance(items, list) or not 1 <= len(items) <= 7 or any(not isinstance(x, str) or x not in TOPICS for x in items):
        raise ValueError("Invalid classifier topics")
    return set(items)


@dataclass
class Reply:
    answer: str
    sources: list[str]
    mode: str
    needs_human: bool

    def as_dict(self):
        return {"answer": self.answer, "sources": self.sources, "mode": self.mode, "needs_human": self.needs_human}


def answer_question(message, router=None):
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Напишите вопрос")
    if len(message) > 2000:
        raise ValueError("Вопрос должен быть не длиннее 2000 символов")
    text = normalize(message)
    topics, order, order_id, unknown = parse_question(text)
    mode = "rules"
    if router is not None:
        try:
            proposed = validate_topics(router(message, system_prompt()))
            # Unambiguous policy cases stay independent of model routing.
            # A model cannot turn an ordinary overdue return into a defect case.
            proposed -= {"discount", "return", "defect"}
            if not topics and proposed != {"greeting"}:
                unknown = True
            topics = proposed | topics
            if re.search(r"(?:x|х)[2-9]\b", text):
                topics.discard("product")
            mode = "llm+policy"
        except Exception:
            # Do not show provider errors or pretend that a model answered.
            mode = "rules-fallback"
    parts, sources = [], []
    needs_human = False

    def add(text, *ids):
        parts.append(text)
        sources.extend(ids)

    if order:
        number = f" №{order_id}" if order_id else ""
        add(f"Не могу проверить заказ{number}: у меня нет доступа к базе заказов, его статусу и индивидуальному сроку доставки.")
        needs_human = True
    if "discount" in topics:
        add(RULES["discount"]["text"] + ", поэтому предоставить скидку или промокод не могу.", "discount")
    if "defect" in topics:
        add("Товар с браком принимаем на экспертизу. Немедленный возврат денег не обещаем; срок и результат экспертизы в регламенте не указаны.", "defect")
        # A defect follows its own rule; do not refuse it because 14 days passed.
        topics.discard("return")
    if "return" in topics:
        days = elapsed_days(text)
        opened = bool(re.search(r"вскры|распак|упаков", text))
        limit = RULES["return"]["days"]
        if len(days) > 1:
            add("В вопросе указано несколько сроков. Уточните, сколько дней прошло: обычный возврат, в том числе вскрытого товара без брака, предусмотрен в течение 14 дней.", "return", "opened")
            needs_human = True
        elif days and max(days) > limit:
            add(f"По регламенту {'вскрытый товар без брака' if opened else 'товар без брака'} можно вернуть в течение {limit} дней. На {max(days)}-й день этот срок уже истёк; обещать такой возврат не могу.", "return", *(["opened"] if opened else []))
        else:
            add(f"{'Вскрытый товар без брака тоже можно вернуть' if opened else 'Возврат предусмотрен'} в течение {limit} дней. Деньги возвращаются {RULES['return']['payment']} за {RULES['return']['refund_business_days']} рабочих дня.", "return", *(["opened"] if opened else []))
    if "product" in topics:
        price = f"{RULES['product']['price_rub']:,}".replace(",", " ")
        availability = "в наличии" if RULES['product']['in_stock'] else "нет в наличии"
        add(f"{RULES['product']['name']} {availability}, цена {price} ₽.", "product")
    if "delivery" in topics:
        prefix = "Общие условия, а не статус вашего заказа: " if order else ""
        add(prefix + "доставка курьером на следующий день, с 18 до 21.", "delivery")
    if "greeting" in topics and not parts:
        add("Здравствуйте! Могу подсказать цену и наличие X1, общие условия доставки, возврата и правила по браку.")
    if unknown or "unknown" in topics or not parts:
        add("Для остальной части вопроса в регламенте нет данных. Это нужно уточнить у сотрудника магазина." if parts else "В регламенте нет информации для ответа на этот вопрос. Уточните, пожалуйста, у сотрудника магазина.")
        needs_human = True
    return Reply("\n\n".join(parts), list(dict.fromkeys(sources)), mode, needs_human)

