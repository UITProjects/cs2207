"""Demo Gathering · buổi hòa nhạc (CS2207 · Nhóm 12).
Chạy: python -m streamlit run app.py   (thuật toán ở gathering_core.py, kiểm tra ở check_core.py)
"""
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gathering_core import DEFAULTS, STEP_MIN, T, VENUE, ZONES, run, time_label

INK, BG, PAPER, LINE = '#172033', '#F5F2EA', '#FCFBF7', '#DDD6C6'
RUST, BLUE, ORANGE, GRAY, MUTE, PEACH, ICE = '#B8541C', '#2D5F9A', '#E08A4F', '#6B7080', '#A3A9B6', '#F3D9C6', '#DCE6F2'
CLUSTER_GRAY = '#7D8494'
# Cr1 đỏ tươi (khác hẳn khung khu vực màu cam), Cr2 xanh dương, Cr3 xanh ngọc: cách nhau cả về sắc lẫn độ sáng
CROWD_COL = ['#D62839', '#1F6FD0', '#0F9D8A', '#8A3FC0', '#C8962E']
NOZOOM = {'scrollZoom': False, 'displaylogo': False}

SUB = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
SUP = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
sub = lambda n: str(n).translate(SUB)
sup = lambda n: str(n).translate(SUP)
cN = lambda i: 'c' + sub(CL[i]['t'] + 1) + sup(CL[i]['k'])   # c_t^k: cụm thứ k tại mốc t
tN = lambda t: 't' + sub(t + 1)
oN = lambda o: 'o' + sub(o[1:])
seq = lambda ids: '⟨' + ', '.join(cN(i) for i in ids) + '⟩'
seq_short = lambda ids: f'⟨{cN(ids[0])} … {cN(ids[-1])}⟩' if len(ids) > 2 else seq(ids)
oset = lambda os: '{' + ', '.join(oN(o) for o in os) + '}' if os else '∅'

st.set_page_config(page_title='Gathering · Hòa nhạc', page_icon='🎵', layout='wide')
st.markdown(f"""<style>
.block-container {{ padding-top: 3.2rem; max-width: 1400px; }}
.kicker {{ color: {RUST}; font-weight: bold; font-size: 13px; letter-spacing: .05em; }}
.q {{ background: {PAPER}; border: 1px solid {LINE}; border-left: 5px solid {INK}; border-radius: 8px;
      padding: 10px 14px; margin: 4px 0 12px; font-size: 16px; line-height: 1.5; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; font-size: 13px; margin-bottom: 10px; }}
.chips b {{ margin-left: 6px; color: #3B4252; }}
.pc {{ border-radius: 10px; padding: 2px 9px; color: #fff; font-weight: bold; }}
.pc.size {{ background: {ORANGE}; }} .pc.close {{ background: {RUST}; }} .pc.dur {{ background: {BLUE}; }}
.verdict {{ border-radius: 10px; padding: 10px 14px; margin: 6px 0 10px; line-height: 1.5; border: 1px solid {LINE}; }}
.verdict.yes {{ background: {ICE}; }} .verdict.no {{ background: {PEACH}; }}
</style>""", unsafe_allow_html=True)

# ----- tham số (người dùng đặt) -----
KEYS = list(DEFAULTS)
with st.sidebar:
    st.markdown('### Tham số\nNgười dùng đặt; thuật toán tìm **mọi** nhóm thỏa chúng.')
    if st.button('↺ Về mặc định', width='stretch'):
        for k in KEYS:
            st.session_state[k] = DEFAULTS[k]
    st.markdown('**① Snapshot cluster · DBSCAN**')
    st.slider(r':red[$\varepsilon$] · bán kính láng giềng (m)', 2.0, 10.0, DEFAULTS['eps'], 0.5, key='eps')
    st.slider(':orange[MinPts] · số điểm tối thiểu', 2, 6, DEFAULTS['min_pts'], key='min_pts')
    st.markdown('**② Crowd**')
    st.slider(':orange[$m_c$] · số người tối thiểu mỗi cụm', 2, 8, DEFAULTS['m_c'], key='m_c')
    st.slider(':blue[$k_c$] · số mốc liên tiếp tối thiểu', 2, T, DEFAULTS['k_c'], key='k_c')
    st.slider(r':red[$\delta$] · Hausdorff tối đa giữa 2 cụm liền (m)', 2.0, 60.0, DEFAULTS['delta'], 1.0, key='delta')
    st.markdown('**③ Gathering**')
    st.slider(':blue[$k_p$] · số cụm một người phải có mặt', 1, T, DEFAULTS['k_p'], key='k_p')
    st.slider(':orange[$m_p$] · participator tối thiểu mỗi cụm', 1, 8, DEFAULTS['m_p'], key='m_p')

P = {k: st.session_state[k] for k in KEYS}
R = run(P)
CL = {c['id']: c for c in R['clusters']}
POS = {(o, t): (x, y) for o, t, x, y in R['rows']}
OBJS = sorted({o for o, *_ in R['rows']}, key=lambda s: int(s[1:]))
crowd_of = {i: k for k, cr in enumerate(R['crowds']) for i in cr}
is_gath = [bool(td['gatherings']) for td in R['tads']]
in_gath = {i for td in R['tads'] for g in td['gatherings'] for i in g}


def gath_par(k):
    """Participators of each gathering TAD returned for crowd k (from the Test that passed)."""
    return [st_['par'] for st_ in R['tads'][k]['trace'] if st_['kind'] == 'test' and not st_['bad']]


def chips():
    p = P
    return ('<div class="chips"><b>DBSCAN:</b>'
            f'<span class="pc close">ε = {p["eps"]:g} m</span><span class="pc size">MinPts = {p["min_pts"]}</span>'
            '<b>Crowd:</b>'
            f'<span class="pc size">m<sub>c</sub> = {p["m_c"]}</span><span class="pc dur">k<sub>c</sub> = {p["k_c"]}</span>'
            f'<span class="pc close">δ = {p["delta"]:g} m</span>'
            '<b>Gathering:</b>'
            f'<span class="pc dur">k<sub>p</sub> = {p["k_p"]}</span><span class="pc size">m<sub>p</sub> = {p["m_p"]}</span></div>')


# ----- hình 3D x–y–t (kiểu Fig. 1c của paper) -----
def circle(c, pad=1.6):
    cx, cy = c['centroid']
    r = max(math.hypot(x - cx, y - cy) for x, y in c['pts']) + pad
    return cx, cy, r


def fig3d(mode, focus=None, view=None):
    """mode: raw | clusters | crowds | participators (focus = index of a crowd).
    view: bộ lọc từ view_controls(): ts = các mốc hiện (list), cl = cụm được chọn (set id, rỗng = tất cả),
    crowd = chỉ crowd này (index, stage 2), lines = nối quỹ đạo, noise = hiện mờ điểm nhiễu (không thuộc cụm nào)."""
    view = view or dict(ts=list(range(T)), cl=set(), crowd=None, lines=True, noise=False)
    ts_vis, sel_cl, lines = view['ts'], view['cl'], view['lines']
    t_lo, t_hi, n_vis = ts_vis[0], ts_vis[-1], len(ts_vis)
    W, H = VENUE
    fig = go.Figure()

    def cluster_shown(c):
        if c['t'] not in ts_vis:
            return False
        if sel_cl and c['id'] not in sel_cl:
            return False
        return view['crowd'] is None or c['id'] in R['crowds'][view['crowd']]

    shown_cl = [c for c in R['clusters'] if mode != 'raw' and cluster_shown(c)]
    for t in ts_vis:
        z = t + 1
        fig.add_trace(go.Mesh3d(x=[0, W, W, 0], y=[0, 0, H, H], z=[z] * 4, i=[0, 0], j=[1, 2], k=[2, 3],
                                color='#CFC6B2', opacity=.16, hoverinfo='skip', showscale=False))
        fig.add_trace(go.Scatter3d(x=[0, W, W, 0, 0], y=[0, 0, H, H, 0], z=[z] * 5, mode='lines',
                                   line=dict(color='#9C9483', width=2), hoverinfo='skip', showlegend=False))
    # khu vực trên mặt phẳng thấp nhất đang hiện
    for name, (x0, y0, x1, y1) in ZONES.items():
        fig.add_trace(go.Scatter3d(x=[x0, x1, x1, x0, x0], y=[y0, y0, y1, y1, y0], z=[t_lo + 1] * 5, mode='lines',
                                   line=dict(color=ORANGE, width=3), hoverinfo='skip', showlegend=False))
        fig.add_trace(go.Scatter3d(x=[(x0 + x1) / 2], y=[y1 + 2.5], z=[t_lo + 1], mode='text', text=[name],
                                   textfont=dict(color='#8A3F14', size=12), hoverinfo='skip', showlegend=False))

    par, members = set(), set()
    if mode == 'participators' and focus is not None and R['tads'][focus]['trace']:
        par = set(R['tads'][focus]['trace'][0]['par'])
        members = {o for i in R['crowds'][focus] for o in CL[i]['members']}

    # cụm (hình elip xám như Fig. 1c)
    if mode != 'raw':
        for c in shown_cl:
            k = crowd_of.get(c['id'])
            col = CLUSTER_GRAY
            if mode in ('crowds', 'participators') and k is not None:
                col = CROWD_COL[k % len(CROWD_COL)]
            if mode == 'participators' and k != focus:
                col = '#C9C3B5'
            cx, cy, r = circle(c)
            a = [2 * math.pi * j / 36 for j in range(36)]
            xs, ys = [cx] + [cx + r * math.cos(v) for v in a], [cy] + [cy + r * math.sin(v) for v in a]
            fig.add_trace(go.Mesh3d(x=xs, y=ys, z=[c['t'] + 1.002] * 37, i=[0] * 36, j=list(range(1, 37)),
                                    k=[j % 36 + 1 for j in range(1, 37)], color=col, opacity=.42, showscale=False,
                                    hovertext=f"{cN(c['id'])} · {tN(c['t'])} · {len(c['members'])} người: {oset(c['members'])}",
                                    hoverinfo='text'))
            fig.add_trace(go.Scatter3d(x=[cx - r - 2.2], y=[cy], z=[c['t'] + 1], mode='text', text=[f"<b>{cN(c['id'])}</b>"],
                                       textfont=dict(color=INK if col != '#C9C3B5' else MUTE, size=14),
                                       hoverinfo='skip', showlegend=False))
    # nối cụm liền nhau có d_H ≤ δ
    if mode == 'crowds':
        for l in R['links']:
            if not l['close']:
                continue
            a, b = CL[l['a']], CL[l['b']]
            if not (cluster_shown(a) and cluster_shown(b)):
                continue
            k = crowd_of.get(l['a'])
            col = CROWD_COL[k % len(CROWD_COL)] if k is not None and crowd_of.get(l['b']) == k else CLUSTER_GRAY
            fig.add_trace(go.Scatter3d(x=[a['centroid'][0], b['centroid'][0]], y=[a['centroid'][1], b['centroid'][1]],
                                       z=[a['t'] + 1, b['t'] + 1], mode='lines', line=dict(color=col, width=7, dash='dash'),
                                       hovertext=f"d_H({cN(l['a'])}, {cN(l['b'])}) = {l['dH']:.1f} m ≤ δ", hoverinfo='text',
                                       showlegend=False))
    # quỹ đạo từng người
    # bước 1–2: chỉ vẽ điểm (người, mốc) nằm trong các cụm đang hiện; điểm nhiễu chỉ hiện mờ khi bật công tắc
    cluster_mode = mode in ('clusters', 'crowds')
    shown_pts = {(o, c['t']) for c in shown_cl for o in c['members']} if cluster_mode else None
    for o in OBJS:
        ts = [t for t in ts_vis if (o, t) in POS]
        if shown_pts is not None:
            ts = [t for t in ts if (o, t) in shown_pts]
        if not ts:
            continue
        line_col, dot, width = ('#8E94A3', '#5A6070', 2) if mode == 'raw' else ('#A9AEB8', '#7A808C', 2)
        if mode == 'participators':
            if o in par:
                line_col, dot, width = ORANGE, ORANGE, 6
            else:
                line_col, dot, width = ('#8E94A3', '#8E94A3', 3) if o in members else ('#CFCAC0', '#B9B4AA', 2)
        xs, ys, zs, hv = [], [], [], []
        for j, t in enumerate(ts):
            if j and t != ts[j - 1] + 1:   # mốc không liền nhau: ngắt đường, không nối xuyên qua mốc bị lọc
                xs.append(None); ys.append(None); zs.append(None); hv.append(None)
            xs.append(POS[o, t][0]); ys.append(POS[o, t][1]); zs.append(t + 1)
            hv.append(f"{oN(o)} · {tN(t)} {time_label(t)} · ({POS[o, t][0]:.1f}, {POS[o, t][1]:.1f})")
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs, mode='lines+markers' if lines else 'markers',
            line=dict(color=line_col, width=width), marker=dict(size=2.8, color=dot),
            hovertext=hv, hoverinfo='text', showlegend=False))
    if cluster_mode and view['noise']:
        clustered = {(o, c['t']) for c in R['clusters'] for o in c['members']}
        nz = [(o, t) for (o, t) in POS if t in ts_vis and (o, t) not in clustered]
        fig.add_trace(go.Scatter3d(
            x=[POS[k][0] for k in nz], y=[POS[k][1] for k in nz], z=[t + 1 for _, t in nz], mode='markers',
            marker=dict(size=2, color='#CFCAC0'), hovertext=[f"{oN(o)} · {tN(t)} · nhiễu" for o, t in nz],
            hoverinfo='text', showlegend=False))
    # ít mốc ⇒ trục t ngắn lại và nhìn từ trên xuống nhiều hơn, để thấy rõ vị trí trên mặt phẳng
    zr = max(0.4, 1.55 * n_vis / T)
    eye = (dict(x=0.35, y=-1.7, z=2.3) if n_vis == 1 else
           dict(x=0.6, y=-2.4, z=1.7) if n_vis <= 3 else dict(x=0.75, y=-3.0, z=1.25))
    rev = f'keep-{min(n_vis, 4)}'   # đổi kiểu xem thì đặt lại camera, cùng kiểu thì giữ góc người dùng xoay
    fig.update_layout(
        height=int(460 + 260 * n_vis / T), margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', uirevision=rev,
        scene=dict(
            xaxis=dict(title='x (m)', range=[-4, W + 4], backgroundcolor=BG, gridcolor=LINE),
            yaxis=dict(title='y (m)', range=[-4, H + 4], backgroundcolor=BG, gridcolor=LINE),
            zaxis=dict(title='t', tickvals=[t + 1 for t in ts_vis], ticktext=[f'{tN(t)} {time_label(t)}' for t in ts_vis],
                       range=[t_lo + 0.7, t_hi + 1.4], backgroundcolor=BG, gridcolor=LINE),
            aspectmode='manual', aspectratio=dict(x=1.3, y=1.04, z=zr),
            camera=dict(eye=eye, center=dict(x=0, y=0, z=-0.08)),
            uirevision=rev))
    return fig


def view_controls(mode):
    """Bộ lọc cho hình 3D (một hàng phía trên hình): mốc thời gian, cụm / crowd, quỹ đạo. Trả về dict `view` cho fig3d."""
    sig = '_'.join(str(P[k]) for k in KEYS)            # đổi tham số ⇒ id cụm đổi ⇒ lọc cũ không còn hợp lệ
    labels = [f'{tN(t)} {time_label(t)}' for t in range(T)]
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.7, 1.6, 1.7, 1.3], vertical_alignment='bottom')
        with c1:
            m = st.segmented_control('Mốc thời gian', ['Tất cả', 'Một mốc', 'Khoảng'], default='Tất cả', key='v_mode') or 'Tất cả'
        with c2:
            if m == 'Một mốc':
                a = st.select_slider('Chọn mốc', labels, value=labels[0], key='v_one')
                lo = hi = labels.index(a)
            elif m == 'Khoảng':
                a, b = st.select_slider('Khoảng mốc', labels, value=(labels[0], labels[-1]), key='v_rng')
                lo, hi = labels.index(a), labels.index(b)
            else:
                lo, hi = 0, T - 1
                st.caption(f'Hiện cả {T} mốc {tN(0)} … {tN(T - 1)}')
        view = dict(ts=list(range(lo, hi + 1)), cl=set(), crowd=None, lines=True, noise=False)
        with c3:
            if mode == 'clusters':
                opts = {cN(c['id']): c['id'] for c in R['clusters'] if lo <= c['t'] <= hi}
                pick = st.multiselect('Chỉ hiện cụm', list(opts), key=f'v_cl_{sig}_{lo}_{hi}', placeholder='Tất cả cụm')
                view['cl'] = {opts[n] for n in pick}
            elif mode == 'crowds' and R['crowds']:
                names = ['Tất cả crowd'] + [f'Cr{sub(k + 1)}' for k in range(len(R['crowds']))]
                pick = st.selectbox('Crowd', names, key=f'v_cr_{sig}')
                view['crowd'] = None if pick == names[0] else names.index(pick) - 1
        with c4:
            view['lines'] = st.toggle('Nối quỹ đạo', value=True, key='v_lines',
                                      help='Tắt để chỉ còn các điểm, ít rối hơn khi trình bày.')
            if mode in ('clusters', 'crowds'):
                view['noise'] = st.toggle('Hiện mờ nhiễu', value=False, key='v_noise',
                                          help='Nhiễu = điểm không thuộc cụm nào ở mốc đó (DBSCAN loại ra). Bật để thấy chúng dạng chấm mờ.')
        if view['crowd'] is not None:
            cr = R['crowds'][view['crowd']]
            st.caption(f"Cr{sub(view['crowd'] + 1)}: {tN(CL[cr[0]]['t'])} → {tN(CL[cr[-1]]['t'])}"
                       + ('' if any(CL[i]['t'] in view['ts'] for i in cr) else ' · ngoài khoảng mốc đang xem'))
    return view


# ----- bản đồ 2D: hướng di chuyển của các crowd -----
def zone_of(p):
    def d(z):
        x0, y0, x1, y1 = z
        return math.hypot(max(x0 - p[0], 0, p[0] - x1), max(y0 - p[1], 0, p[1] - y1))
    return min(ZONES, key=lambda n: d(ZONES[n]))


def zone_dist(p, z):
    x0, y0, x1, y1 = z
    return math.hypot(max(x0 - p[0], 0, p[0] - x1), max(y0 - p[1], 0, p[1] - y1))


def route(cr, near=10):
    """Zones the crowd passes, in order: nearest zone of each centroid within `near` m, no repeats."""
    out = []
    for i in cr:
        p = CL[i]['centroid']
        z = min(ZONES, key=lambda n: zone_dist(p, ZONES[n]))
        if zone_dist(p, ZONES[z]) <= near and (not out or out[-1] != z):
            out.append(z)
    return ' → '.join(out) if len(out) > 1 else f'đứng yên ở {out[0]}' if out else '—'


def direction(cr):
    a, b = CL[cr[0]]['centroid'], CL[cr[-1]]['centroid']
    moved = math.hypot(b[0] - a[0], b[1] - a[1])
    za, zb = zone_of(a), zone_of(b)
    if moved < 5:
        return f'đứng yên ở {za}', moved
    return f'{za} → {zb}', moved


def fig2d():
    W, H = VENUE
    fig = go.Figure()
    fig.add_shape(type='rect', x0=0, y0=0, x1=W, y1=H, line=dict(color='#9C9483', width=2), fillcolor=PAPER, layer='below')
    for name, (x0, y0, x1, y1) in ZONES.items():
        fig.add_shape(type='rect', x0=x0, y0=y0, x1=x1, y1=y1, line=dict(color=ORANGE, width=1.5),
                      fillcolor='rgba(243,217,198,.55)', layer='below')
        fig.add_annotation(x=(x0 + x1) / 2, y=y1 + 1.8, text=name, showarrow=False, font=dict(color='#8A3F14', size=13))
    # mọi điểm thô, mờ
    fig.add_trace(go.Scatter(x=[r[2] for r in R['rows']], y=[r[3] for r in R['rows']], mode='markers',
                             marker=dict(size=4, color='#CFCAC0'), hoverinfo='skip', showlegend=False))
    for k, cr in enumerate(R['crowds']):
        col = CROWD_COL[k % len(CROWD_COL)]   # màu = crowd; đặc/liền = thuộc gathering, rỗng/nét đứt = chỉ là crowd
        for i in cr:
            cx, cy, r = circle(CL[i], pad=1.0)
            ok = i in in_gath
            fig.add_shape(type='circle', x0=cx - r, y0=cy - r, x1=cx + r, y1=cy + r,
                          line=dict(color=col, width=2 if ok else 1.5, dash='solid' if ok else 'dot'),
                          fillcolor=col if ok else 'rgba(0,0,0,0)', opacity=.28 if ok else .95)
        xs = [CL[i]['centroid'][0] for i in cr]
        ys = [CL[i]['centroid'][1] for i in cr]
        # đoạn đứng yên (tâm cách nhau < 3 m) chỉ có một nhãn ở cụm cuối: c₅¹ … c₁₀¹
        labels, start = [''] * len(cr), 0
        for j in range(1, len(cr) + 1):
            if j == len(cr) or math.dist(CL[cr[j]]['centroid'], CL[cr[start]]['centroid']) >= 3:
                labels[j - 1] = cN(cr[start]) if j - 1 == start else f'{cN(cr[start])} … {cN(cr[j - 1])}'
                start = j
        # Cr1 nhãn phía trên, crowd khác phía dưới: chỗ hai crowd đi qua cùng một điểm không đè chữ lên nhau
        pos = ['top center' if k == 0 else 'bottom center'] * len(cr)
        if direction(cr)[1] < 5:
            labels[-1], pos[-1] = f'  Cr{sub(k + 1)} · {labels[-1]} · đứng yên', 'middle right'
        dashed_x, dashed_y = [], []
        for j in range(len(cr) - 1):
            if math.dist(CL[cr[j]]['centroid'], CL[cr[j + 1]]['centroid']) < 2:
                continue
            both = cr[j] in in_gath and cr[j + 1] in in_gath
            if both:   # liền, dày: đoạn thuộc gathering
                fig.add_annotation(x=xs[j + 1], y=ys[j + 1], ax=xs[j], ay=ys[j], xref='x', yref='y', axref='x', ayref='y',
                                   showarrow=True, arrowhead=3, arrowsize=1.2, arrowwidth=3, arrowcolor=col,
                                   text='', standoff=4, startstandoff=4)
            else:      # nét đứt mảnh + mũi tên ngắn ở đầu: đoạn chỉ là crowd
                d = math.dist((xs[j], ys[j]), (xs[j + 1], ys[j + 1]))
                f = min(1.0, 4.0 / d)
                dashed_x += [xs[j], xs[j + 1], None]
                dashed_y += [ys[j], ys[j + 1], None]
                fig.add_annotation(x=xs[j + 1], y=ys[j + 1], ax=xs[j + 1] - f * (xs[j + 1] - xs[j]),
                                   ay=ys[j + 1] - f * (ys[j + 1] - ys[j]), xref='x', yref='y', axref='x', ayref='y',
                                   showarrow=True, arrowhead=3, arrowsize=1.2, arrowwidth=1.8, arrowcolor=col,
                                   text='', standoff=4, startstandoff=0)
        if dashed_x:
            fig.add_trace(go.Scatter(x=dashed_x, y=dashed_y, mode='lines', line=dict(color=col, width=1.8, dash='dash'),
                                     hoverinfo='skip', showlegend=False))
        kind = ('Gathering' if R['tads'][k]['gatherings'] == [cr] else
                'Gathering ' + ', '.join(seq(g) for g in R['tads'][k]['gatherings']) if is_gath[k] else 'chỉ là crowd')
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode='markers+text',
            marker=dict(size=10, color=[col if i in in_gath else '#fff' for i in cr], line=dict(color=col, width=2)),
            text=labels, textposition=pos, textfont=dict(size=12, color=col),
            hovertext=[f'{cN(i)} · {time_label(CL[i]["t"])} · {oset(CL[i]["members"])}' for i in cr],
            hoverinfo='text', name=f"Cr{sub(k + 1)} · {kind}"))
    fig.update_layout(height=600, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor=BG,
                      legend=dict(orientation='h', y=-0.08, x=0), font=dict(color=INK))
    fig.update_xaxes(range=[-2, W + 2], title='x (m)', showgrid=False, zeroline=False, constrain='domain')
    fig.update_yaxes(range=[-2, H + 4], title='y (m)', showgrid=False, zeroline=False, scaleanchor='x', scaleratio=1)
    return fig


# ----- bảng bit vector của một crowd -----
def bit_table(k):
    cr, td = R['crowds'][k], R['tads'][k]
    t0 = td['trace'][0]
    rows = []
    for o in td['objs']:
        n = sum(td['B'][o])
        ok = o in t0['par']
        rows.append({'Người': oN(o), 'Vai trò': R['role'][o],
                     **{cN(i): str(b) for i, b in zip(cr, td['B'][o])},
                     '# bit 1': str(n), 'Participator?': f'✓ {n} ≥ kₚ' if ok else f'✗ {n} < kₚ'})
    rows.insert(0, {'Người': 'Σ', 'Vai trò': 'participator / cụm',
                 **{cN(i): f"{n} {'✓' if n >= P['m_p'] else '✗'}" for i, n in zip(cr, t0['counts'])},
                 '# bit 1': '', 'Participator?': f'cần ≥ mₚ = {P["m_p"]}'})
    df = pd.DataFrame(rows)

    def style(row):
        if row['Người'] == 'Σ':
            return ['font-weight: bold; background-color: #EEE8DC'] * len(row)
        if str(row['Participator?']).startswith('✓'):
            return [f'background-color: #FBEBDD; color: {INK}'] * len(row)
        return [f'color: {GRAY}'] * len(row)
    return df.style.apply(style, axis=1)


def tad_story(k):
    cr, td = R['crowds'][k], R['tads'][k]
    mp = f"m<sub>p</sub> = {P['m_p']}"
    lines = []
    for step in td['trace']:
        ids = [cr[i] for i in range(len(cr)) if step['mask'][i]]
        if step['kind'] == 'test':
            cnt = ', '.join(f'{cN(cr[i])}: {n}' for i, n in enumerate(step['counts']) if n is not None)
            line = f"<b>Test</b> {seq(ids)}: Par = {oset(step['par'])} · participator mỗi cụm: {cnt}"
            if not step['bad']:
                line += f" ⇒ mọi cụm ≥ {mp} ⇒ <b>Gathering ✓</b> (closed, Theorem 1)"
            else:
                line += f" ⇒ cụm hỏng: {', '.join(cN(cr[i]) for i in step['bad'])} (< {mp})"
        else:
            parts = '; '.join(f"{seq([cr[i] for i in range(len(cr)) if p['mask'][i]])} dài {p['tau']} "
                              + ('≥ k<sub>c</sub> ⇒ Test lại' if p['ok'] else '< k<sub>c</sub> ⇒ bỏ') for p in step['parts'])
            line = f"<b>Divide</b>: cắt {', '.join(cN(cr[i]) for i in step['bad'])} ⇒ {parts or 'không còn đoạn nào'}"
        lines.append(f'<li>{line}</li>')
    if not td['gatherings']:
        lines.append(f'<li>⇒ <b>Không có gathering</b> trong Cr{sub(k + 1)}: đông nhưng không phải cùng những người đó ở lại.</li>')
    cls = 'yes' if td['gatherings'] else 'no'
    return f'<div class="verdict {cls}"><b>Test-and-Divide trên Cr{sub(k + 1)}</b><ul style="margin:4px 0 0">{"".join(lines)}</ul></div>'


# ----- trang -----
st.markdown('<div class="kicker">CS2207 · NHÓM 12 · DEMO GATHERING</div>', unsafe_allow_html=True)
st.title('Gathering: tìm nhóm tụ họp ở buổi hòa nhạc')

STAGES = ['0 · Dữ liệu thô', '1 · Cụm theo mốc', '2 · Nối thành Crowd', '3 · Kiểm tra Gathering', '4 · Kết quả']
stage = st.segmented_control('Bước', STAGES, default=STAGES[0], label_visibility='collapsed') or STAGES[0]
s = STAGES.index(stage)
st.markdown(chips(), unsafe_allow_html=True)

n_people = len(OBJS)
if s == 0:
    minutes = (T - 1) * STEP_MIN
    st.markdown(f'<div class="q">Buổi hòa nhạc {time_label(0)} → {time_label(T - 1)} ({minutes // 60}h{minutes % 60:02d}): '
                f'<b>{n_people} người</b>, vị trí (x, y) ghi mỗi {STEP_MIN} phút, {T} mốc {tN(0)} … {tN(T - 1)}. '
                '<br><b>Câu hỏi:</b> làm sao khai phá dữ liệu này để ra các <b>Crowd = ⟨c₁ᵏ, c₂ᵏ, c₃ᵏ, …⟩</b>, '
                'và crowd nào thật sự là một <b>Gathering</b>?</div>', unsafe_allow_html=True)
    view = view_controls('raw')
    left, right = st.columns([1.5, 1])
    with left:
        st.plotly_chart(fig3d('raw', view=view), width='stretch', key='g3d', config=NOZOOM)
    with right:
        df = pd.DataFrame([(o, tN(t), time_label(t), x, y) for o, t, x, y in R['rows']],
                          columns=['Người', 'Mốc', 'Giờ', 'x (m)', 'y (m)'])
        st.markdown(f'**Dữ liệu thô** · {len(df)} điểm (người, mốc, x, y)')
        st.dataframe(df, hide_index=True, height=470, width='stretch')
        st.download_button('⬇ Tải CSV', df.to_csv(index=False).encode('utf-8-sig'), 'concert_points.csv', 'text/csv')

elif s == 1:
    st.markdown(f'<div class="q">Ở <b>mỗi mốc</b>, gom những người đứng gần nhau bằng <b>DBSCAN</b> '
                f'(ε = {P["eps"]:g} m, MinPts = {P["min_pts"]}). Mỗi nhóm là một <b>snapshot cluster</b> (Definition 1).'
                '<br><b>Ký hiệu c<sub>t</sub><sup>k</sup></b>: cluster thứ k tại mốc t. Chỉ số dưới là mốc, như '
                'c<sub>t<sub>i</sub></sub> trong Definition 2; chỉ số trên phân biệt các cluster cùng một mốc '
                '(ví dụ c₁¹, c₁² đều ở t₁).</div>', unsafe_allow_html=True)
    view = view_controls('clusters')
    left, right = st.columns([1.5, 1])
    with left:
        st.plotly_chart(fig3d('clusters', view=view), width='stretch', key='g3d', config=NOZOOM)
    with right:
        rows = [{'Cụm': cN(c['id']), 'Mốc': tN(c['t']), 'Số người': f"{len(c['members'])} {'✓' if len(c['members']) >= P['m_c'] else '✗'}",
                 'Thành viên': oset(c['members'])} for c in R['clusters']]
        st.markdown(f"**{len(rows)} snapshot cluster** · ✓ = ≥ m<sub>c</sub> = {P['m_c']} người", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        inc = {o for c in R['clusters'] for o in c['members']}
        lone = sorted({o for o, *_ in R['rows'] if o not in inc}, key=lambda s_: int(s_[1:]))
        st.caption(f"Không thuộc cụm nào ở mọi mốc (nhiễu): {oset(lone)}.")

elif s == 2:
    st.markdown(f'<div class="q">Nối cụm ở hai mốc <b>liền nhau</b> nếu khoảng cách Hausdorff '
                f'd<sub>H</sub> ≤ δ = {P["delta"]:g} m (vị trí và hình dạng gần giống). Chuỗi dài ≥ k<sub>c</sub> = {P["k_c"]} '
                f'mốc, cụm nào cũng ≥ m<sub>c</sub> = {P["m_c"]} người ⇒ <b>Crowd</b> (Definition 2, Algorithm 1 tìm '
                'closed crowd).</div>', unsafe_allow_html=True)
    view = view_controls('crowds')
    left, right = st.columns([1.5, 1])
    with left:
        st.plotly_chart(fig3d('crowds', view=view), width='stretch', key='g3d', config=NOZOOM)
    with right:
        st.markdown('**Crowd tìm được**')
        if not R['crowds']:
            st.warning('Không có crowd nào với tham số hiện tại.')
        for k, cr in enumerate(R['crowds']):
            col = CROWD_COL[k % len(CROWD_COL)]
            st.markdown(f'<span style="color:{col};font-weight:bold;font-size:17px">Cr{sub(k + 1)} = {seq(cr)}</span>'
                        f' · {tN(CL[cr[0]]["t"])} → {tN(CL[cr[-1]]["t"])} · {len(cr)} mốc', unsafe_allow_html=True)
        in_crowd = {i for cr in R['crowds'] for i in cr}
        left_out = [c['id'] for c in R['clusters'] if c['id'] not in in_crowd]
        if left_out:
            st.caption(f"Cụm không vào crowd nào: {', '.join(cN(i) for i in left_out)} "
                       f"(chuỗi nối được ngắn hơn k_c = {P['k_c']} mốc, hoặc cụm < m_c người).")
        show_all = st.toggle('Hiện mọi cặp (kể cả cặp không nối)', value=False)
        rows = [{'Cặp': f"{cN(l['a'])} → {cN(l['b'])}", 'Mốc': f"{tN(CL[l['a']]['t'])} → {tN(CL[l['b']]['t'])}",
                 'd_H (m)': round(l['dH'], 1), f'≤ δ = {P["delta"]:g}?': '✓ nối' if l['close'] else '✗'}
                for l in R['links'] if show_all or l['close']]
        st.markdown(f"**Hausdorff giữa các cụm ở hai mốc liền nhau** · {len(rows)} cặp")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', height=330)
    st.markdown('<div class="verdict no">Crowd chỉ nói <b>"chỗ này luôn đông"</b>. Chưa biết có phải '
                '<b>cùng những người đó</b> ở lại không ⇒ bước 3.</div>', unsafe_allow_html=True)

elif s == 3:
    if not R['crowds']:
        st.warning('Không có crowd nào để kiểm tra. Thử nới tham số ở bước 1–2.')
    else:
        st.markdown(f'<div class="q">Mỗi người có một <b>bit vector</b>: bit = 1 nếu có mặt trong cụm đó. '
                    f'Có mặt ≥ k<sub>p</sub> = {P["k_p"]} cụm (không cần liên tiếp) ⇒ <b>participator</b>. '
                    f'Cụm nào cũng có ≥ m<sub>p</sub> = {P["m_p"]} participator ⇒ <b>Gathering</b> '
                    '(Definition 3–4, thuật toán Test-and-Divide).</div>', unsafe_allow_html=True)
        names = [f"Cr{sub(k + 1)} = {seq_short(cr)}" for k, cr in enumerate(R['crowds'])]
        pick = st.radio('Crowd', names, horizontal=True, label_visibility='collapsed')
        k = names.index(pick)
        st.dataframe(bit_table(k), hide_index=True, width='stretch', height=35 * (min(len(R['tads'][k]['objs']), 12) + 2) + 3)
        st.caption('Dòng Σ = số participator trong từng cụm. Bảng cuộn được khi crowd có nhiều người.')
        left, right = st.columns([1, 1.2])
        with left:
            st.markdown(tad_story(k), unsafe_allow_html=True)
        with right:
            st.plotly_chart(fig3d('participators', k), width='stretch', key='g3d', config=NOZOOM)
            st.caption('Cam = participator của crowd đang chọn; xám = có mặt nhưng chưa đủ k_p cụm.')

else:
    st.markdown('<div class="q"><b>Kết quả:</b> danh sách crowd, crowd nào là gathering, và lộ trình mỗi nhóm đi qua.</div>',
                unsafe_allow_html=True)
    rows = []
    for k, (cr, td) in enumerate(zip(R['crowds'], R['tads'])):
        gs = td['gatherings']
        rows.append({'Crowd': f'Cr{sub(k + 1)}', 'Chuỗi cụm': seq_short(cr), 'Lộ trình': route(cr),
                     'Thời gian': f"{time_label(CL[cr[0]]['t'])} → {time_label(CL[cr[-1]]['t'])} ({len(cr)} mốc)",
                     'Gathering': ('✓ cả crowd' if gs == [cr] else '✓ ' + ', '.join(seq_short(g) for g in gs)) if gs else '✗ chỉ là crowd',
                     'Participator của gathering': ' | '.join(oset(p) for p in gath_par(k)) if gs else '—'})
    if rows:
        df = pd.DataFrame(rows)
        # st.table wraps long cells (the full route), st.dataframe would cut them
        def row_style(r):
            base = (f'background-color: {ICE}; font-weight: bold' if r['Gathering'].startswith('✓') else f'color: {GRAY}')
            return [f'{base}; color: {CROWD_COL[r.name % len(CROWD_COL)]}; font-weight: bold'
                    if c == 'Crowd' else base for c in r.index]
        st.table(df.style.apply(row_style, axis=1).hide(axis='index'))
    else:
        st.warning('Không có crowd nào với tham số hiện tại.')
    st.plotly_chart(fig2d(), width='stretch', key='g2d', config=NOZOOM)
    st.caption('Mỗi crowd một màu. Hình tròn đặc + mũi tên liền dày = cụm thuộc gathering; vòng rỗng nét chấm + mũi tên nét đứt = cụm của crowd nhưng không thuộc gathering.')
    lines = []
    for k, (cr, td) in enumerate(zip(R['crowds'], R['tads'])):
        name = f'<b>Cr{sub(k + 1)}</b> ({route(cr)})'
        for g, par in zip(td['gatherings'], gath_par(k)):
            span = f"{time_label(CL[g[0]]['t'])} → {time_label(CL[g[-1]]['t'])}"
            if g == cr:
                lines.append(f'{name}: <b>Gathering</b> cả crowd, {span}. {oset(par)} ở lại cùng nhau.')
            else:
                cut = [i for i in cr if i not in g]
                lines.append(f'{name}: chỉ đoạn {seq(g)} ({span}) là <b>Gathering</b> với {oset(par)}; '
                             f'{", ".join(cN(i) for i in cut)} bị cắt vì người đến rồi đi.')
        if not td['gatherings']:
            lines.append(f'{name}: lúc nào cũng có một nhóm đi cùng nhau, nhưng người đến rồi đi ⇒ <b>chỉ là crowd</b>.')
    if lines:
        st.markdown('<div class="verdict">' + '<br>'.join(lines) + '</div>', unsafe_allow_html=True)
