"""Apply LaTeX-style math typography to visible labels, never to data keys."""
import re
from matplotlib.text import Text

REPLACEMENTS = {
    'Qbar(p) = sum p_i Q_i': r'$\bar{Q}(p)=\sum_i p_i Q_i$',
    'Qbar': r'$\bar{Q}$',
    'p_rob': r'$p_{\mathrm{rob}}$',
    'p*': r'$p^{*}$',
    'Q_lin': r'$Q_{\mathrm{lin}}$',
    'Q_res': r'$Q_{\mathrm{res}}$',
    'Q_i': r'$Q_i$',
    'p_i': r'$p_i$',
    'a_i': r'$a_i$',
    'g_i(p)': r'$g_i(p)$',
    'beta': r'$\beta$',
    'rho=': r'$\rho$=',
    'R2': r'$R^2$',
}

def format_math_labels(fig):
    """MathText renders LaTeX syntax without requiring an external TeX runtime."""
    for artist in fig.findobj(match=Text):
        original = artist.get_text()
        # Leave existing math spans intact; format only plain-text spans.
        spans = re.split(r'(\$[^$]*\$)', original)
        for i in range(0, len(spans), 2):
            pattern = '|'.join(re.escape(k) for k in REPLACEMENTS)
            spans[i] = re.sub(pattern, lambda m: REPLACEMENTS[m.group()], spans[i])
        updated = ''.join(spans)
        if updated != original:
            artist.set_text(updated)
            artist.set_math_fontfamily('stix')
