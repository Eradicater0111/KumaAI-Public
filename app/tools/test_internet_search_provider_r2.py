from urllib.parse import quote

from app.tools.internet_tools import (
    _internet1_r2_parse_results,
)


def test_r2_parses_ddg_web_result_h2_link():
    payload = '''
    <div id="links">
      <div class="web-result">
        <h2>
          <a href="https://example.com/a">
            Example Result
          </a>
        </h2>
        <a class="result__snippet">
          Example snippet.
        </a>
      </div>
    </div>
    '''

    results = _internet1_r2_parse_results(
        payload,
        5,
    )

    assert results[0]["title"] == "Example Result"
    assert results[0]["url"] == "https://example.com/a"


def test_r2_parses_ddg_lite_result_link():
    payload = '''
    <a href="https://example.com/b"
       class="result-link">
       Lite Result
    </a>
    '''

    results = _internet1_r2_parse_results(
        payload,
        5,
    )

    assert results[0]["title"] == "Lite Result"
    assert results[0]["url"] == "https://example.com/b"


def test_r2_parser_ignores_attribute_order():
    payload = '''
    <a href="https://example.com/c"
       data-x="1"
       class="result__a">
       Attribute Order
    </a>
    '''

    results = _internet1_r2_parse_results(
        payload,
        5,
    )

    assert results[0]["title"] == "Attribute Order"


def test_r2_decodes_ddg_redirect_target():
    target = "https://example.com/story"

    payload = f'''
    <a class="result__a"
       href="//duckduckgo.com/l/?uddg={quote(target, safe='')}">
       Redirect Result
    </a>
    '''

    results = _internet1_r2_parse_results(
        payload,
        5,
    )

    assert results[0]["url"] == target
