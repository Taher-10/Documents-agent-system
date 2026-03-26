# Set to True to print per-document heading score distribution at end of run.
_DEBUG_SCORES = False
_score_log = []  # populated by score_heading_probability when _DEBUG_SCORES=True

HEADER_FOOTER_ZONE      = 0.15 #the height of which a header or footer usually occupie
HEADER_FOOTER_THRESHOLD = 0.3 
HEADER_FOOTER_MAX_CHARS = 500 #the maximum number of characters a header or footer can have

FONT_GAP_TOLERANCE      = 0.5 
MIN_HEADING_CHARS_FLOOR = 100 #the minimum number of characters a heading can have
MIN_HEADING_CHARS_PCT   = 0.001 

HEADING_SCORE_THRESHOLD            = 4
HEADING_STRUCTURAL_SCORE_THRESHOLD = 6

SHORT_TEXT_THRESHOLD    = 80
UPPERCASE_RATIO_THRESHOLD = 0.7
VERTICAL_GAP_MULTIPLIER = 1.5

SAMPLE_PAGES = 200 #sample of the number of pages to be processed for detection

