from artemis_mobile_agent.ui import denormalized, normalized, parse_elements

def test_parse_and_coordinates():
    xml = '<hierarchy><node text="Battery" resource-id="battery" class="TextView" clickable="true" bounds="[100,200][300,400]"/></hierarchy>'
    e = parse_elements(xml)
    assert e[0].text == "Battery"
    assert e[0].center == (200, 300)
    assert denormalized(normalized((200, 300), 1000, 1000), 1000, 1000) == (200, 300)
