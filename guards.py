"""Deterministic checks for critical policy errors in generated text."""
import re
import unicodedata


def normalize(text):
    return unicodedata.normalize("NFKC", text).lower().replace("ё", "е")


def context(message):
    text = normalize(message)
    days = {int(n) for n in re.findall(r"\b(\d{1,4})\s*(?:[-–]?\s*(?:й|ый|ой|го|ом|му)\s*)?(?:день|дня|дней|дню|дне|суток|сутки)\b", text)}
    for root, number in (("шестнадцат", 16), ("пятнадцат", 15), ("четырнадцат", 14), ("тринадцат", 13)):
        if re.search(root + r"\w*\s+(?:день|дня|дней|дню|дне)", text):
            days.add(number)
    if "две недели" in text:
        days.add(14)
    if "три недели" in text:
        days.add(21)
    without_negation = re.sub(r"без\s+брака|без\s+дефектов|брака\s+нет|дефектов\s+нет|не\s+бракован\w*|\bисправн\w*", "", text)
    defect = bool(re.search(r"брак|дефект|не\s*работа|неисправ|сломан|поломан", without_negation))
    other_product = any(n != "1" for n in re.findall(r"\b[xх]\s*(\d+)\b", text))
    unknown = other_product or bool(re.search(r"цвет|сини|черн|белы|красн|гарант|адрес|город|минск|москв|совместим|bluetooth|блют|заряд|батаре|аккум|водонепрон|влагозащ|\bipx?\d|бесплатн|стоимость\s+достав|сколько\s+стоит\s+достав|(?:достав\w*|привез\w*)\s+(?:в|во|до|по)\s+[а-яa-z]", text))
    order = bool(re.search(r"заказ|трек(?:инг)?|моя\s+посылк|мой\s+возврат", text))
    order_ids = {int(n) for n in re.findall(r"заказ\w*\s*(?:№|номер|#)?\s*(\d{1,12})\b", text)}
    return {
        "days": days, "order": order, "order_ids": order_ids, "defect": defect,
        "return": bool(re.search(r"верну|возврат|верне|вскры|распак|упаков", text)),
        "opened": bool(re.search(r"вскры|распак|упаков", text)),
        "discount": bool(re.search(r"скид|промокод|дисконт|дешевле|discount", text)),
        "unknown": unknown, "other_product": other_product,
    }


def lacks_information(text):
    return bool(re.search(r"нет\s+(?:доступа|данных|информации|сведений)|не\s+(?:указан|располага|извест|знаю)|не\s*могу\s+(?:проверить|подтвердить|сообщить|уточнить|определить)", text))


def check_answer(message, draft, rules):
    if not isinstance(draft, dict) or set(draft) != {"answer", "source_ids", "needs_human"}:
        return ["invalid_schema"]
    answer, ids = draft["answer"], draft["source_ids"]
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 1800 or not isinstance(ids, list) or any(not isinstance(i, str) or i not in rules for i in ids) or len(set(ids)) != len(ids) or type(draft["needs_human"]) is not bool:
        return ["invalid_schema"]
    text = normalize(answer)
    ctx = context(message)
    errors = []
    if not ids and (not lacks_information(text) or not draft["needs_human"]):
        errors.append("missing_sources_or_unknown")
    compact_numbers = re.sub(r"(?<=\d)[\s,.](?=\d{3}(?!\d))", "", text)
    supplied_skus = set(re.findall(r"\b[xх]\s*(\d+)\b", normalize(message)))
    number_text = re.sub(r"\b[xх]\s*(\d+)\b", lambda match: "sku" if match[1] in supplied_skus else match[0], compact_numbers)
    allowed = {1, rules["product"]["price_rub"], rules["return"]["days"], rules["return"]["refund_business_days"], 18, 21} | ctx["days"] | ctx["order_ids"]
    numbers = {int(n) for n in re.findall(r"\d+", number_text)}
    if numbers - allowed or "%" in text:
        errors.append("unsupported_number")
    if re.search(r"₽|рубл", text) and 2490 not in numbers and not lacks_information(text):
        errors.append("unsupported_price")
    if re.search(r"не\s+обещай|скажи\s+(?:клиенту|пользователю)|верни\s+json|needs_human|source_ids", text):
        errors.append("instruction_in_answer")
    if re.search(r"аккум|батаре|bluetooth|блют|цвет|гаранти|бесплатн", text) and not lacks_information(text):
        errors.append("unsupported_attribute")
    if re.search(r"оформил|оформлен|передал|передан|нашел\s+(?:ваш\s+)?заказ|проверил\s+(?:ваш\s+)?заказ|создал\s+заявк", text):
        errors.append("invented_action")
    if ctx["order"]:
        if not lacks_information(text) or not draft["needs_human"]:
            errors.append("order_status_not_unknown")
        if re.search(r"следующ|завтр|\b(?:18|21)\b", text) and not re.search(r"общ(?:ие|им|их|ий)\s+услов|по\s+общему\s+правил", text):
            errors.append("order_delivery_promise")
        if re.search(r"заказ.{0,25}(?:доставлен|отправлен|оплачен|собран|у\s+курьера|готов)", text):
            errors.append("invented_order_status")
    if ctx["discount"] and not re.search(r"скид(?:ок|ки)\s+нет|скид\w*.{0,25}не\s+(?:предусмотр|предостав|делаем|даем)|не\s+(?:предостав|делаем|даем).{0,20}скид", text):
        errors.append("discount_not_refused")
    if ctx["defect"]:
        if "экспертиз" not in text:
            errors.append("missing_examination")
        if re.search(r"(?:сразу|немедленно).{0,25}(?:вернем|возвращаем|выплатим)|(?:вернем|возвращаем|выплатим).{0,25}(?:сразу|немедленно)|3\s+рабоч", text):
            errors.append("defect_payout_promise")
    elif ctx["return"] and ctx["days"] and max(ctx["days"]) > rules["return"]["days"]:
        if not re.search(r"истек|просроч|за\s+пределами|не\s+(?:можем|могу|предусмотрен|принимаем)|нельзя|невозмож", text):
            errors.append("overdue_return_not_refused")
    if ctx["opened"] and not ctx["defect"] and (not ctx["days"] or max(ctx["days"]) <= rules["return"]["days"]):
        if re.search(r"вскрыт\w*.{0,35}(?:нельзя|невозможно|не\s+принимаем)", text):
            errors.append("opened_return_wrongly_refused")
    if ctx["unknown"] and (not lacks_information(text) or not draft["needs_human"]):
        errors.append("missing_unknown")
    product_claim = re.sub(r"не\s+указан[а-я]*\s+в\s+наличии", "", text)
    if ctx["other_product"] and re.search(r"в\s+наличии|2490|2\s*490", product_claim):
        errors.append("wrong_product")
    if re.search(r"\b3\s+дн", text) and "рабоч" not in text:
        errors.append("refund_days_not_business")
    if 2490 in numbers and "product" not in ids:
        errors.append("wrong_sources")
    if re.search(r"\b(?:18|21)\b|курьер", text) and "delivery" not in ids:
        errors.append("wrong_sources")
    return list(dict.fromkeys(errors))
