from PIL import ImageFont


def test_find_font_prefers_bundled(dlm):
    regular = dlm._find_font_file(bold=False)
    bold = dlm._find_font_file(bold=True)
    assert regular is not None and 'assets' in regular
    assert regular.endswith('DejaVuSans.ttf')
    assert bold is not None and bold.endswith('DejaVuSans-Bold.ttf')


def test_load_fonts_returns_truetype(dlm):
    fonts = dlm.load_fonts()
    assert isinstance(fonts['temp'], ImageFont.FreeTypeFont)
