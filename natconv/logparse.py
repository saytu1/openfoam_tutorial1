import re

_RE_TAVG = re.compile(r"areaAverage\(heater\) of T = ([-\d.eE+]+)")
_RE_TMAX = re.compile(r"max\(heater\) of T = ([-\d.eE+]+)")
_RE_QR = re.compile(r"areaAverage\(heater\) of qr = ([-\d.eE+]+)")


def parse_convergence(log_text):
    """솔버 로그에서 히터 표면 T 평균·최대, 복사 qr 시계열 추출."""
    T_avg = [float(x) for x in _RE_TAVG.findall(log_text)]
    T_max = [float(x) for x in _RE_TMAX.findall(log_text)]
    qr = [float(x) for x in _RE_QR.findall(log_text)]
    iters = list(range(1, len(T_avg) + 1))
    return {"iters": iters, "T_avg": T_avg, "T_max": T_max, "qr": qr}
