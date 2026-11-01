# Draws docs/hbridge.svg: the reused H-bridge from the original IKEA controller board.
#   pip install schemdraw matplotlib   then   python3 docs/hbridge_schematic.py
import os
import schemdraw
import schemdraw.elements as elm

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hbridge.svg")
W = 9.0          # distance between the two legs
TOP = 11.0       # V+ rail
BOT = 0.0        # GND rail
YL = 4.6         # height of the strip (L1/L2 outputs)
FS = 11          # label font size

schemdraw.config(fontsize=FS, lw=1.3)
with schemdraw.Drawing(show=False) as d:
    # ---- high side: P-MOSFETs, gates facing inward ----
    q3 = elm.PFet().theta(0).anchor("source").at((0, TOP - 0.6))
    q4 = elm.PFet().theta(0).reverse().anchor("source").at((W, TOP - 0.6))
    d += q3; d += q4
    d += elm.Line().at(q3.source).to((0, TOP))
    d += elm.Line().at(q4.source).to((W, TOP))
    # ---- low side: N-MOSFETs, gates facing outward ----
    q2 = elm.NFet().theta(0).reverse().anchor("source").at((0, BOT + 0.6))
    q1 = elm.NFet().theta(0).anchor("source").at((W, BOT + 0.6))
    d += q2; d += q1
    for q, name, part, side in ((q3, "Q3", "AO3401 P-ch", -1), (q2, "Q2", "AO3400 N-ch", 1),
                                (q4, "Q4", "AO3401 P-ch", 1), (q1, "Q1", "AO3400 N-ch", -1)):
        x = q.center[0] + side * 0.35
        d += elm.Label().at((x, q.center[1])).label(name + "\n" + part, halign="left" if side > 0 else "right", fontsize=FS - 1)
    d += elm.Line().at(q2.source).to((0, BOT))
    d += elm.Line().at(q1.source).to((W, BOT))

    # ---- outputs L1 (left leg) and L2 (right leg) ----
    d += elm.Line().at(q3.drain).to(q2.drain)
    d += elm.Line().at(q4.drain).to(q1.drain)
    d += elm.Dot().at((0, YL)).label("L1", loc="left", ofst=(-0.1, 0))
    d += elm.Dot().at((W, YL)).label("L2", loc="right", ofst=(0.1, 0))

    # ---- the strip: anti-parallel LEDs between L1 and L2 ----
    a, b = 2.2, W - 2.2
    d += elm.Line().at((0, YL)).to((a, YL))
    d += elm.Line().at((b, YL)).to((W, YL))
    d += elm.Line().at((a, YL - 0.7)).to((a, YL + 0.7))
    d += elm.Line().at((b, YL - 0.7)).to((b, YL + 0.7))
    d += elm.LED().at((a, YL + 0.7)).to((b, YL + 0.7)).label("A: lights when L1 is +", loc="top")
    d += elm.LED().at((b, YL - 0.7)).to((a, YL - 0.7)).label("B: lights when L2 is +", loc="bottom")
    x0, x1, y0, y1 = a - 0.6, b + 0.6, YL - 2.45, YL + 2.45
    for p0, p1 in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        d += elm.Line().at(p0).to(p1).linestyle("--").color("gray").linewidth(0.8)
    d += elm.Label().at(((a + b) / 2, YL - 2.8)).label("LED strip (2 wires, LEDs anti-parallel)", color="gray", fontsize=FS - 1)

    # ---- high-side gate networks: 2k to V+, 10k cross-coupled to the OPPOSITE output ----
    n3 = (q3.gate[0] + 0.9, q3.gate[1])
    n4 = (q4.gate[0] - 0.9, q4.gate[1])
    d += elm.Line().at(q3.gate).to(n3); d += elm.Dot().at(n3)
    d += elm.Line().at(q4.gate).to(n4); d += elm.Dot().at(n4)
    d += elm.Resistor().at(n3).to((n3[0], TOP)).label("2k", loc="bottom")
    d += elm.Resistor().at(n4).to((n4[0], TOP)).label("2k", loc="top")
    yc = YL + 2.6        # where the cross resistors meet the legs
    d += elm.Resistor().at(n3).to((W, yc)).label("10k", loc="top", ofst=0.15)
    d += elm.Resistor().at(n4).to((0, yc)).label("10k", loc="top", ofst=0.15)
    d += elm.Dot().at((W, yc)); d += elm.Dot().at((0, yc))

    # ---- low-side gate drive: 1k from the Pico, 10k pull-down ----
    g2 = (q2.gate[0] - 1.0, q2.gate[1])
    g1 = (q1.gate[0] + 1.0, q1.gate[1])
    d += elm.Line().at(q2.gate).to(g2); d += elm.Dot().at(g2)
    d += elm.Line().at(q1.gate).to(g1); d += elm.Dot().at(g1)
    d += elm.Resistor().at(g2).to((g2[0] - 3, g2[1])).label("1k", loc="top")
    d += elm.Resistor().at(g1).to((g1[0] + 3, g1[1])).label("1k", loc="top")
    d += elm.Dot(open=True).at((g2[0] - 3, g2[1])).label("GP1\n(Pico pin 2)", loc="left")
    d += elm.Dot(open=True).at((g1[0] + 3, g1[1])).label("GP0\n(Pico pin 1)", loc="right")
    d += elm.Resistor().at(g2).to((g2[0], BOT)).label("10k", loc="bottom")
    d += elm.Resistor().at(g1).to((g1[0], BOT)).label("10k", loc="top")

    # ---- rails ----
    d += elm.Line().at((-3.2, TOP)).to((W, TOP))
    d += elm.Diode().at((-3.2, TOP)).to((-6.2, TOP)).reverse().label("D2", loc="top")
    d += elm.Dot(open=True).at((-6.2, TOP)).label("24 V in\n(V+)", loc="left")
    d += elm.Label().at((W / 2, TOP + 0.45)).label("V+", fontsize=FS)
    d += elm.Line().at((g2[0], BOT)).to((g1[0], BOT))
    d += elm.Ground().at((W / 2, BOT))
    d += elm.Label().at((W / 2 + 0.3, BOT - 1.0)).label("GND (V−) = Pico GND", halign="left", fontsize=FS - 1)
    d.save(OUT, transparent=False)
print("wrote", OUT)
