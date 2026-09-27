import json

import pytest

from assistants import chatbot_tools
from assistants.chatbot_tools import build_tools, fallback, find_packages, is_arabic, my_offer
from assistants.llm import ToolCall
from assistants.service_client import ServiceError


def row(offer_id, price, hours, name_en, **fields):
    base = {
        "offer_id": offer_id,
        "operator": "Almadar Aljadid",
        "name_ar": f"ar {name_en}",
        "name_en": name_en,
        "family_en": "Family",
        "price_lyd": price,
        "validity_ar": "شهر",
        "validity_hours": hours,
        "data_gb": None,
        "data_unlimited": False,
        "voice_minutes": None,
        "voice_unlimited": False,
        "network": None,
        "valid_from_hour": None,
        "valid_to_hour": None,
        "collected": "2026-09-18",
    }
    return base | fields


CATALOGUE = [
    row("HR5G_1", 5.0, 1, "Net 1 hour 5G", data_unlimited=True, network="5G"),
    row("M5G_100", 120.0, 720, "Net 100 5G", data_gb=100.0, network="5G"),
    row("MO_20", 35.0, 720, "Net 20", data_gb=20.0),
    row("FAM_70", 90.0, 720, "Family 70", data_gb=70.0, voice_minutes=300.0),
    row(
        "SABAH_1",
        1.0,
        24,
        "Morning",
        data_unlimited=True,
        voice_unlimited=True,
        valid_from_hour=6.0,
        valid_to_hour=11.0,
    ),
    row("SOC_M", 20.0, 720, "Social monthly"),
]

OFFER = {
    "subscriber_id": "70016",
    "recommended_offer_id": "SABAH_1",
    "offer_reason_en": "Catalogue bonus: Morning (06:00-11:00).",
    "offer_reason_ar": "مكافأة من الكتالوج: الصبح (06:00-11:00).",
    "reviewed_at": "2026-09-22T10:00:00+00:00",
    "campaign_id": "abc123",
    "offer": CATALOGUE[4],
}


class FakeClient:
    def __init__(self, offer=None, error=None):
        self.offer, self.error, self.asked = offer, error, []

    def catalogue(self, base_url, key):
        if self.error:
            raise self.error
        return CATALOGUE

    def offer_for(self, base_url, key, subscriber_id):
        self.asked.append((base_url, key, subscriber_id))
        if self.error:
            raise self.error
        return self.offer


def ids(result):
    return [package["offer_id"] for package in result["packages"]]


def test_packages_are_cheapest_first_by_default():
    assert ids(find_packages(CATALOGUE)) == ["SABAH_1", "HR5G_1", "SOC_M", "MO_20", "FAM_70"]
    assert find_packages(CATALOGUE)["matched"] == 6


def test_filters_are_applied_in_code():
    assert ids(find_packages(CATALOGUE, needs="voice")) == ["SABAH_1", "FAM_70"]
    assert ids(find_packages(CATALOGUE, needs="data_and_voice", period="month")) == ["FAM_70"]
    assert ids(find_packages(CATALOGUE, network="5G", max_price_lyd="10")) == ["HR5G_1"]
    assert ids(find_packages(CATALOGUE, period="hours")) == ["HR5G_1"]
    assert find_packages(CATALOGUE, needs="any", network="any", period="any")["matched"] == 6


def test_sorting_by_data_puts_unlimited_first():
    assert ids(find_packages(CATALOGUE, needs="data", sort="most_data"))[:3] == [
        "HR5G_1",
        "SABAH_1",
        "M5G_100",
    ]


def test_a_package_is_described_in_plain_values():
    morning = find_packages(CATALOGUE, needs="voice")["packages"][0]
    assert morning["data"] == "unlimited" and morning["voice"] == "unlimited"
    assert morning["daily_window"] == "06:00-11:00"
    assert (
        find_packages(CATALOGUE, max_price_lyd=35, sort="most_data")["packages"][2]["data"]
        == "20 GB"
    )


def test_a_bad_price_is_an_error_the_model_sees():
    with pytest.raises(ValueError):
        find_packages(CATALOGUE, max_price_lyd="cheap")


def test_my_offer_hides_the_ids_and_the_price():
    client = FakeClient(offer=OFFER)
    result = my_offer("http://service", "chatbot-key", "70016", True, client)
    assert client.asked == [("http://service", "chatbot-key", "70016")]
    text = json.dumps(result, ensure_ascii=False)
    assert "70016" not in text and "abc123" not in text
    assert "price" not in result["offer"]["package"]
    assert result["offer"]["reason"] == OFFER["offer_reason_ar"]


def test_no_offer_and_no_sign_in_say_so():
    assert my_offer("u", "k", "70017", client=FakeClient(offer=None))["offer"] is None
    client = FakeClient(offer=OFFER)
    assert "not signed in" in my_offer("u", "k", None, client=client)["say"]
    assert client.asked == []


def test_my_offer_takes_no_arguments_and_is_bound_to_the_session():
    client = FakeClient(offer=OFFER)
    tools = {tool.name: tool for tool in build_tools("u", "k", "70016", client=client)}
    assert tools["my_offer"].parameters["properties"] == {}
    tools["my_offer"].run()
    tools["my_offer"].run()
    # Read fresh every time: an offer is never cached (integration.md rule 6).
    assert client.asked == [("u", "k", "70016")] * 2


def test_the_chatbot_has_exactly_its_three_tools():
    names = [tool.name for tool in build_tools("u", "k", "70016", client=FakeClient())]
    assert names == ["find_packages", "my_offer", "find_service_point"]


def test_without_a_sign_in_there_is_no_offer_tool_to_misread():
    names = [tool.name for tool in build_tools("u", "k", None, client=FakeClient())]
    assert names == ["find_packages", "find_service_point"]
    assert "not signed in" in chatbot_tools.system_prompt(False, signed_in=False)
    assert "is signed in" in chatbot_tools.system_prompt(False)


def test_service_points_wait_for_their_data():
    assert chatbot_tools.find_service_point("Tripoli")["available"] is False


def test_fallback_uses_only_tool_data_in_the_customers_language():
    client = FakeClient(offer=OFFER)
    offer_ar = ToolCall("my_offer", {}, my_offer("u", "k", "70016", True, client))
    offer = ToolCall("my_offer", {}, my_offer("u", "k", "70016", False, client))
    arabic = fallback([offer_ar], "في عرض ليا؟")
    assert arabic == "مكافأة من الكتالوج: الصبح (06:00-11:00). - ar Morning"
    assert fallback([offer], "any offer?") == "Catalogue bonus: Morning (06:00-11:00). - Morning"
    none = ToolCall("my_offer", {}, {"offer": None, "say": "..."})
    assert fallback([none], "any offer?") == "There is no offer for you today."
    packages = ToolCall("find_packages", {}, find_packages(CATALOGUE, network="5G"))
    assert fallback([packages], "5G?") == "- Net 1 hour 5G: 5 LYD\n- Net 100 5G: 120 LYD"
    error = ToolCall("find_packages", {}, {"error": "The service is not available right now."})
    assert "not available" in fallback([error], "5G?")
    assert "customer service" in fallback([], "what is my balance?")
    assert "خدمة عملاء" in fallback([], "كم رصيدي؟")


def test_service_errors_surface_from_the_bound_tools():
    tools = build_tools("u", "k", "70016", client=FakeClient(error=ServiceError("down", 503)))
    with pytest.raises(ServiceError):
        tools[0].run()


def test_arabic_detection():
    assert is_arabic("شن أرخص باقة؟") and not is_arabic("cheapest package?")


def test_results_come_in_one_language_only():
    english = find_packages(CATALOGUE, needs="voice")["packages"][0]
    assert english["name"] == "Morning" and english["validity"] == "1 day"
    assert "name_ar" not in english and "validity_ar" not in english
    arabic = find_packages(CATALOGUE, True, needs="voice")["packages"][0]
    assert arabic["name"] == "ar Morning" and arabic["validity"] == "1 يوم"
    assert find_packages(CATALOGUE, period="hours")["packages"][0]["validity"] == "1 hour"
    assert find_packages(CATALOGUE, period="month")["packages"][0]["validity"] == "30 days"


def test_the_bound_language_reaches_both_tools():
    client = FakeClient(offer=OFFER)
    tools = {tool.name: tool for tool in build_tools("u", "k", "70016", True, client)}
    assert tools["find_packages"].run(needs="voice")["packages"][0]["name"] == "ar Morning"
    assert tools["my_offer"].run()["offer"]["reason"] == OFFER["offer_reason_ar"]


def test_validity_and_amounts_read_naturally_in_each_language():
    by_id = {row["offer_id"]: row for row in CATALOGUE}
    three_days = row("DAY_QTR", 2.0, 72, "Net 1/4", data_gb=0.25)
    assert chatbot_tools.package_view(three_days, True)["validity"] == "3 أيام"
    assert chatbot_tools.package_view(three_days, False)["validity"] == "3 days"
    assert chatbot_tools.package_view(by_id["M5G_100"], True)["validity"] == "30 يوم"
    assert chatbot_tools.package_view(by_id["M5G_100"], True)["data"] == "100 جيجا"
    family = chatbot_tools.package_view(by_id["FAM_70"], True)
    assert family["voice"] == "300 دقيقة"
    assert chatbot_tools.package_view(by_id["SABAH_1"], True)["data"] == "غير محدود"


def test_the_prompt_names_the_detected_language():
    assert "Write your whole reply in Arabic.\n" in chatbot_tools.system_prompt(True)
    assert "latest message is in English" in chatbot_tools.system_prompt(False)


def test_the_customer_chooses_how_many_up_to_ten():
    many = [row(f"P{i:02d}", float(i), 720, f"Package {i}", data_gb=1.0) for i in range(1, 16)]
    assert len(find_packages(many)["packages"]) == 5
    ten = find_packages(many, count=10)
    assert len(ten["packages"]) == 10 and ten["shown"] == 10 and ten["matched"] == 15
    assert len(find_packages(many, count=40)["packages"]) == 10
    assert len(find_packages(many, count="3")["packages"]) == 3
    assert find_packages(CATALOGUE, network="5G", count=10)["shown"] == 2


def test_the_order_used_is_named():
    assert find_packages(CATALOGUE)["order"] == "cheapest first"
    assert find_packages(CATALOGUE, sort="most_data")["order"] == "most data first"
    assert find_packages(CATALOGUE, sort="longest")["order"] == "longest validity first"


def test_every_optional_argument_accepts_null():
    """Groq checks tool calls against the schema, and the model fills unused fields with null."""
    tools = {tool.name: tool for tool in build_tools("u", "k", "70016", client=FakeClient())}
    for name in ("find_packages", "find_service_point"):
        for field, spec in tools[name].parameters["properties"].items():
            assert "null" in spec["type"], (name, field)
            if "enum" in spec:
                assert None in spec["enum"], (name, field)
    nulls = dict.fromkeys(tools["find_packages"].parameters["properties"])
    assert tools["find_packages"].run(**nulls)["shown"] == 5


def test_prices_are_written_in_the_reply_language():
    by_id = {row["offer_id"]: row for row in CATALOGUE}
    assert chatbot_tools.package_view(by_id["MO_20"], False)["price"] == "35 LYD"
    assert chatbot_tools.package_view(by_id["MO_20"], True)["price"] == "35 دينار"
    assert "LYD" not in str(find_packages(CATALOGUE, True, count=10))


def test_an_unstated_volume_is_not_called_no_data():
    social = {row["offer_id"]: row for row in CATALOGUE}["SOC_M"]
    assert chatbot_tools.package_view(social, False)["data"] == "volume not stated by Almadar"
    assert chatbot_tools.package_view(social, True)["data"] == "الحجم غير محدد من المدار"


def test_not_signed_in_asks_to_sign_in_instead_of_saying_no_offer():
    result = my_offer("u", "k", None, client=FakeClient(offer=OFFER))
    call = ToolCall("my_offer", {}, result)
    assert fallback([call], "any offer?").endswith("Sign in to see them.")
    assert "سجّل الدخول" in fallback([call], "في عرض؟")
    assert "no offer" not in fallback([call], "any offer?").casefold()


def test_the_prompt_names_the_operator_in_each_language():
    assert "Almadar in English and المدار in Arabic" in chatbot_tools.SYSTEM_PROMPT


def test_another_account_number_is_noticed_in_code():
    assert chatbot_tools.mentions_other_account("What offer does subscriber 70016 have?", "70017")
    assert chatbot_tools.mentions_other_account("شوف رقم ٠٩١ ٢٣٤ ٥٦٧٨", "70017")
    assert not chatbot_tools.mentions_other_account("Is 70016 my offer?", "70016")
    assert not chatbot_tools.mentions_other_account("10 packages under 50 LYD", "70016")
    prompt = chatbot_tools.system_prompt(False, other_account=True)
    assert "only check the customer's own account" in prompt
    assert "not the signed-in" not in chatbot_tools.system_prompt(False)
