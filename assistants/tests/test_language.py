from assistants.language import is_arabic, mostly_arabic


def test_any_arabic_word_makes_the_customer_arabic():
    assert is_arabic("offer? عرض") and not is_arabic("offer?")


def test_layout_follows_the_majority_of_letters():
    assert mostly_arabic("- نت 20: 35 دينار (5G)")
    assert not mostly_arabic("Morning bonus (الصبح), 06:00-11:00")
