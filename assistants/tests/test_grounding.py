from assistants.grounding import has_phone_number, numbers, ungrounded


def test_numbers_are_canonical():
    assert numbers("5 LYD, 5.0 LYD and 5.00 LYD") == {"5"}
    assert numbers("0.25 GB for 2.5 dinars") == {"0.25", "2.5"}


def test_arabic_indic_digits_and_marks_are_read():
    assert numbers("السعر ٥ دينار و ٠٫٢٥ جيجا") == {"5", "0.25"}
    assert numbers("۱۲۰ دينار") == {"120"}


def test_thousands_separators_are_not_decimals():
    assert numbers("1,060,786 GB") == {"1060786"}
    assert numbers("٬ 1٬200 GB") == {"1200"}
    assert numbers("2,5 LYD") == {"2.5"}
    # The model groups thousands with narrow, thin and no-break spaces too.
    assert numbers("68 900 people, 1 111 492 GB") == {"68900", "1111492"}
    # An ordinary space still separates two numbers.
    assert numbers("rank 1 of 20 212") == {"1", "20", "212"}


def test_a_number_from_a_tool_or_the_user_is_grounded():
    tool = '{"price_lyd": 5.0, "daily_window": "06:00-11:00"}'
    assert ungrounded("It costs 5 LYD, from 06:00 to 11:00.", [tool]) == set()
    assert (
        ungrounded("You asked about 50%: I cannot change prices.", ["Give me 50% off", tool])
        == set()
    )


def test_an_invented_number_is_caught():
    tool = '{"price_lyd": 5.0}'
    assert ungrounded("It costs 4 LYD.", [tool]) == {"4"}
    assert ungrounded("السعر ٤ دينار", [tool]) == {"4"}


def test_list_markers_are_not_figures():
    tool = '{"name_en": "Net 20", "price_lyd": 35}'
    assert ungrounded("1. Net 20: 35 LYD\n2) Net 20 again", [tool]) == set()


def test_nothing_is_grounded_without_sources():
    assert ungrounded("Call 1234", []) == {"1234"}
    assert ungrounded("No numbers here.", []) == set()


def test_phone_numbers_are_found_however_they_are_written():
    assert has_phone_number("call 0912345678")
    assert has_phone_number("+218 94 123 4567")
    assert has_phone_number("٠٩٢١٢٣٤٥٦٧")
    assert not has_phone_number("subscriber 70016, 1,060,786 GB")
