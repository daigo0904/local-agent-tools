from util import fmt_date


def invoice_header(no, y, m, d):
    return "請求書 No.%d 発行日 %s" % (no, fmt_date(y, m, d))
