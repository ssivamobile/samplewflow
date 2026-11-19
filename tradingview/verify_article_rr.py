"""Checks the R:R arithmetic and the Model 1 TP rules against the six annotated charts in the article
(values read off pages 9, 12, 17, 20, 22, 23). Run: python3 tradingview/verify_article_rr.py"""
# Values read off the article's annotated charts (pages 9, 12, 17, 20, 22, 23)
# name: (side, entry, stop, target, labelled_R, vah, val, tp1_label)
cases = {
 "P9  Model1 schematic": ("S", 62.00,    72.00,    37.00,    2.5, 63.00,    37.00,    50.00),
 "P12 Model2 schematic": ("L", 61.00,    55.00,    81.54,    3.4, None,     None,     None),
 "P17 NQ Trade1 (M2)":   ("S", 25662.00, 25677.00, 25602.00, 4.0, None,     None,     None),
 "P20 ES Trade2 (M1)":   ("S", 6965.00,  6968.50,  6953.50,  3.3, 6965.00,  6953.50,  None),
 "P22 NQ NFP long":      ("L", 25790.00, 25775.00, 25824.75, 2.3, None,     None,     None),
 "P23 NQ M1 day":        ("S", 25905.00, 25920.00, 25862.00, 2.9, 25908.00, 25862.00, 25885.00),
}
print(f"{'case':24}{'risk':>8}{'reward':>9}{'R calc':>8}{'R label':>9}  TP1 mid check")
for k,(s,e,st,t,lab,vah,val,tp1) in cases.items():
    risk=abs(e-st); rew=abs(t-e); r=rew/risk
    extra=""
    if vah is not None and val is not None:
        mid=(vah+val)/2; r1=abs(e-mid)/risk
        extra=f"mid=(VAH+VAL)/2={mid:.2f}" + (f" label={tp1:.2f}" if tp1 else "") + f"  TP1 R={r1:.2f}  target==VAL:{abs(t-val)<1e-9}"
    print(f"{k:24}{risk:8.2f}{rew:9.2f}{r:8.2f}{lab:9.1f}  {extra}")
