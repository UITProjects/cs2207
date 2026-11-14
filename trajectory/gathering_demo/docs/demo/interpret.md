# Presenter guide: how to run and narrate the demo

A script for presenting the web demo live. It explains how to read every screen and what to say so the audience
follows the story. The UI is in Vietnamese; labels are quoted exactly as they appear (e.g. **Bộ dữ liệu**).
Suggested lines in Vietnamese are given in *italics*: adapt them freely.

**Total time: 6–8 minutes.** One idea per screen: *data → algorithm → result → why it matters*.

---

## 1. Before you go on stage (5 minutes earlier)

- [ ] Open the demo link and wait for the first 3D chart to appear (this warms the server cache for everyone).
- [ ] Sidebar check:
  - [ ] **Bộ dữ liệu** = *PGS 12 Grand Final · 5 trận*;
  - [ ] **Trận** = *Trận 3 · 31/10 10:32 · 28:45 ★* (★ = the showcase match);
  - [ ] **Hiện tên đội / người chơi** is on.
- [ ] Open both pages once: 🔬 **Thuật toán**, then 🎯 **Kết quả**, then come back to 🔬 **Thuật toán**.
- [ ] Press **↺ Về mặc định** so every parameter is at its default.
- [ ] Browser zoom 90–100%; hide bookmarks; full screen (F11). Close other tabs (3D uses the GPU).
- [ ] **Fallbacks:**
  - if 3D is slow on the projector, use the **Kiểu xem → 🗺️ 2D** switch;
  - if the network fails, run locally with `docker run -p 8501:8501 <image>` and open `http://localhost:8501/`;
  - the **Mock** dataset always works.

---

## 2. The story arc

### Step 1: Hook (30 s), sidebar visible
Point at the badge **REAL · PGS 12 Grand Final**.

> *"Đây là dữ liệu thật của chung kết PGS 12: 64 tuyển thủ chuyên nghiệp, 16 đội, gần 29 phút. Câu hỏi của
> chúng tôi: các đội thật sự **tụ lại** ở đâu và khi nào, và ai chỉ **đi ngang qua**?"*

### Step 2: The data (30 s)
- Every player's position is recorded every **10 seconds**, so this match is a set of trajectories (x, y, t).
- It comes from the official PUBG API. The sidebar's **Bộ dữ liệu** also offers the two newest tournaments (SEA PACP26, SEA PACI26) and a simulated match.

> *"Mỗi chấm là vị trí của một người chơi, cứ 10 giây một lần. Cả trận là khoảng 6 000 điểm như vậy."*

### Step 3: The algorithm, 🔬 Thuật toán (3–4 min)
The page opens in **🧊 3D x–y–t**. Spend the first 20 seconds teaching the audience how to read the cube, and it pays off for the rest of the demo:

| In the cube | Meaning |
|---|---|
| Floor | the Erangel map |
| Vertical axis | time (bottom = start of the window) |
| A **vertical** line | a player standing still |
| A **slanted** line | a player moving (flatter = faster) |
| Colour | the team (legend on top; team tag such as `T1`, `VIT`) |

> *"Trục đứng là thời gian. Đường thẳng đứng nghĩa là đứng yên, đường nghiêng là đang di chuyển."*

Then walk through the four tabs. The default view is the first crowd: Mylta, around 07:50–09:30.

1. **① Quỹ đạo**: raw trajectories in the window. Use **Đội** to keep 2–3 teams; the scene becomes readable at once.
2. **② Cụm snapshot**: at every 10-second slice, **DBSCAN** groups nearby players (eps = 150 m). Each grey **disc** is one cluster; darker discs have ≥ m_c = 8 people (at least two squads).
   > *"Mỗi lát cắt ngang là một thời điểm; mỗi đĩa là một nhóm người đứng gần nhau."*
3. **③ Crowd**: discs at consecutive times are linked when their **Hausdorff distance d_H ≤ δ = 300 m** (dashed links; hover shows d_H). A chain lasting ≥ k_c = 6 steps (60 s) is a **crowd**. The bar chart on the right shows every d_H below the δ line.
   > *"Crowd là một chuỗi nhóm nối tiếp nhau đủ lâu: hình dạng và vị trí thay đổi rất ít giữa hai thời điểm."*
4. **④ Gathering**: a crowd can be made of people passing through. **Test-and-Divide** keeps only the **participators** (people present in ≥ k_p = 4 clusters). Thick solid lines are teams with participators; thin dashed lines are teams that only passed by. The TAD box shows the test result; the bar chart shows participators per cluster against m_p.
   > *"Gathering là crowd mà phần lớn người ở lại thật sự, không chỉ đi ngang qua."*

**Live parameter moment (optional, 45 s).** Pick one, then press **↺ Về mặc định**:
- **Crowd but not a gathering:** set **eps** 150 → **100** and open **④ Gathering**. Now 6 crowds give only 5 gatherings: Cr1 (Mylta, 08:30–09:20) fails the test, is divided, and nothing survives.
  > *"Đông người nhưng không phải cùng một nhóm ở lại, nên không phải gathering."*
- **Divide in action:** set **m_p** 6 → **8** and **k_p** 4 → **6**. In **④ Gathering**, Cr1 shows *Test → Divide → Test*: the violating cluster is cut and the gathering shrinks to 07:50–09:20.

### Step 4: The result, 🎯 Kết quả (2 min)
Click the link at the bottom (*Xem kết quả →*) or **Kết quả** in the menu.

1. **The strip at the top** reads left to right:
   > *"64 người → khoảng 6 200 điểm → 666 cụm → 7 crowd → **7 gathering** → 14 đội tham gia."*

   Blue boxes are the mining steps; orange boxes are the output.
2. **🗺️ Di chuyển → Đường đi**: one line per followed team (default: the 3 teams in the most gatherings, T1, TYL and VIT). ● marks landing, ■ the end of the trajectory, small labels every 3 minutes.
   - T1: Gatka → Prison → Mylta Power (6.5 km).
   - TYL: Novorepnoye → East Bridge → Mylta (3.9 km).
   - VIT: Georgopol → Mylta (6.8 km).
   > *"Ba đội xuất phát từ ba góc bản đồ khác nhau nhưng cùng hội tụ về Mylta."*
3. **Replay** (optional): pick a team in **Bám theo đội** and press ▶; the camera follows that team, with a 60-second trail.
4. **3D x–y–t**: the whole match as one cube. Orange columns are the gatherings; you can see the late game pile up into one tall column at Mylta.
5. **🎯 Gathering tab**: the timeline. Read it top to bottom:
   - G1–G3 (07:50–11:50) are small: 2–3 teams, 8–10 participators;
   - G4 and G5 (12:30–15:30) grow to 7–8 teams and 21–23 participators;
   - **G6 (15:50–28:30)** lasts almost 13 minutes with 9 teams and 24 participators: the final-circle contest.
   
   Select one and switch **Kiểu xem** between **3D** and **2D**. The box on the right lists, per team, how many players were present and how many were participators.

### Step 5: Takeaway (30 s)
> *"Từ dữ liệu vị trí thô, thuật toán tự động tìm ra **ở đâu, khi nào** các đội thật sự tụ lại, và **ai** là người
> ở lại hay chỉ đi ngang qua: điều mà xem lại video không làm được ở quy mô lớn. Cùng phương pháp này dùng được
> cho đám đông ở sự kiện, giao thông, hay đàn động vật."*

---

## 3. Legend cheat sheet

| Symbol | Where | Meaning |
|---|---|---|
| ★ | match picker | showcase match (best gathering coverage) |
| ● / ■ | routes, 3D | start (landing) / end of a trajectory |
| grey / dark disc | ② Cụm snapshot | cluster with fewer / at least m_c players |
| light-orange disc | ③ Crowd | cluster belonging to the selected crowd |
| dashed dark line | ③ Crowd | link between consecutive clusters, d_H ≤ δ |
| light-blue disc | ④ Gathering | cluster kept in the gathering after TAD |
| thick solid / thin dashed | ④ Gathering (team lines) | team with participators / team that only passed by |
| blue circle / white dashed circle | 2D maps, replay | current zone / next zone |
| orange column | 🎯 Kết quả → 3D | a gathering over time |
| bar colour (blue → orange) | gathering timeline | early → late phase |

## 4. Parameters in one sentence each
- **eps, min_pts**: how close (m) and how many neighbours make a DBSCAN cluster.
- **m_c**: minimum cluster size for a crowd (8 = at least two squads, so one squad walking together is not a crowd).
- **δ**: maximum Hausdorff distance between consecutive clusters (how much a group may move or change shape in 10 s).
- **k_c**: minimum crowd duration in 10-second steps (6 = 1 minute).
- **k_p**: how many clusters a player must appear in to count as a participator.
- **m_p**: minimum participators in every cluster of a gathering.

## 5. Likely questions
- **Why 10 seconds?** That's the rate at which PUBG records positions. It suits group movement, not gunfights.
- **Why Hausdorff distance?** It compares whole groups (shape and position), not just centroids, so a group that splits or stretches is detected.
- **Crowd vs gathering?** A crowd is "many people here for a while". A gathering additionally requires that mostly the *same* people stay (participators).
- **Why do many gatherings sit around one place?** The final zones of this match were around Mylta, so the late game converges there. Early gatherings are rotations, the late ones the final circle.
- **Is it real data?** Yes: the official PUBG Developer API, tournament shard. Names are the players' in-game names, and the data is used under the PUBG API terms.
- **Limitations:** 10-second sampling; one match is an illustration, not a statistical result; place names come from an approximate gazetteer.
- **Branch variants?** When a group splits into two disjoint groups at several moments, the algorithm produces many equivalent closed crowds. The app merges the ones with the same time span and the same people.

## 6. Do and don't
- **Do** filter to 2–3 teams before explaining a 3D view, and rotate slowly, explaining once the view is still.
- **Do** keep **↺ Về mặc định** in mind after every parameter change.
- **Don't** run the replay on a slow projector machine; use **Đường đi** or **3D** instead.
- **Don't** read the numbers aloud from the tables; point at the strip and the timeline.
