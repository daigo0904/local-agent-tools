from util import fmt_date


def report_line(title, y, m, d):
    return "%s（%s）" % (title, fmt_date(y, m, d).replace("/", "-"))
