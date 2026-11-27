"""The Spark apps' palette (BotWatch's, as in Spark Media and Spark Launcher) as GTK 4 CSS."""

BG, PANEL, PANEL2, HOVER = '#04090b', '#0a1517', '#0e1f22', '#12292c'
LINE, LINE2 = '#143a3d', '#1f6a66'
TEXT, MUTED, DIM = '#d4f1ec', '#6f9f98', '#3b6460'
ACCENT, ON_ACCENT = '#3de8c8', '#02130f'
PINK, GOLD = '#ff4d8d', '#f4c95d'
CH_A, CH_B = '#ff2e88', '#22d8ff'
MONO = 'Cascadia Mono'

CSS = f"""
* {{ font-family: "{MONO}", monospace; }}
window.spark-panel {{ background: {BG}; color: {TEXT}; border-top: 1px solid {LINE}; }}
window.spark-panel.top {{ border-top: none; border-bottom: 1px solid {LINE}; }}
window.spark-wallpaper {{ background: {BG}; }}
window.spark-transparent {{ background: transparent; }}
window.spark-scrim {{ background: rgba(4,9,11,0.78); }}
.spark-label {{ font-size: 9pt; font-weight: bold; color: {MUTED}; letter-spacing: 1px; }}
.spark-text {{ color: {TEXT}; font-size: 10pt; }}
.spark-dim {{ color: {DIM}; font-size: 9pt; }}
button.spark-btn {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {LINE};
  border-radius: 3px; padding: 4px 10px; min-height: 0; box-shadow: none; font-size: 9pt;
  font-weight: bold; }}
button.spark-btn:hover, button.spark-btn:focus {{ background: {HOVER}; border-color: {LINE2};
  box-shadow: 2px 0 0 {CH_A}, -2px 0 0 {CH_B}; }}
button.spark-primary {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; }}
button.spark-primary:hover {{ background: #8cf5e2; }}
button.spark-danger {{ color: {PINK}; }}
button.spark-flat {{ background: transparent; border: 1px solid transparent; border-radius: 3px;
  color: {TEXT}; padding: 2px 6px; min-height: 0; box-shadow: none; }}
button.spark-flat:hover {{ background: {HOVER}; border-color: {LINE}; }}
button.spark-task {{ background: transparent; border: 1px solid transparent; border-radius: 3px;
  padding: 2px 8px; min-height: 0; color: {MUTED}; box-shadow: none; }}
button.spark-task:hover {{ background: {HOVER}; border-color: {LINE2}; color: {TEXT}; }}
button.spark-task.running {{ color: {TEXT}; border-bottom: 2px solid {LINE2}; }}
button.spark-task.active {{ background: {PANEL2}; border-color: {LINE2};
  border-bottom: 2px solid {ACCENT}; color: {TEXT}; }}
button.spark-task.attention {{ border-bottom: 2px solid {PINK}; }}
button.spark-launcher-btn {{ background: {PANEL2}; color: {ACCENT}; border: 1px solid {LINE2};
  border-radius: 3px; padding: 2px 12px; min-height: 0; font-weight: bold; letter-spacing: 2px;
  box-shadow: none; }}
button.spark-launcher-btn:hover {{ box-shadow: 3px 0 0 {CH_A}, -3px 0 0 {CH_B}; }}
button.spark-ws {{ background: transparent; border: 1px solid transparent; border-radius: 3px;
  padding: 0 6px; min-height: 0; min-width: 0; color: {DIM}; font-size: 9pt; box-shadow: none; }}
button.spark-ws:hover {{ background: {HOVER}; border-color: {LINE}; color: {TEXT}; }}
button.spark-ws.occupied {{ color: {MUTED}; border-bottom: 2px solid {LINE2}; }}
button.spark-ws.current {{ background: {PANEL2}; border-color: {LINE2};
  border-bottom: 2px solid {ACCENT}; color: {TEXT}; }}
button.spark-ws-tile {{ color: {DIM}; }}
button.spark-ws-tile.on {{ color: {ACCENT}; }}
button.drop-before {{ box-shadow: inset 2px 0 0 {CH_B}; }}
button.drop-after {{ box-shadow: inset -2px 0 0 {CH_A}; }}
.spark-dot {{ font-size: 10pt; }}
.spark-dot.ok {{ color: {ACCENT}; }}
.spark-dot.warn {{ color: {GOLD}; }}
.spark-dot.down {{ color: {PINK}; }}
.spark-dot.rebooting {{ color: {MUTED}; }}
.spark-dot.unknown {{ color: {DIM}; }}
.spark-count {{ font-size: 9pt; font-weight: bold; color: {TEXT}; }}
.spark-clock {{ font-size: 11pt; font-weight: bold; color: {TEXT}; }}
popover.spark-pop > contents {{ background: {PANEL}; color: {TEXT};
  border: 1px solid {LINE2}; border-radius: 3px; padding: 6px;
  box-shadow: 3px 0 0 {CH_A}, -3px 0 0 {CH_B}; }}
popover.spark-pop button.spark-item {{ background: transparent; border: none; border-radius: 3px;
  color: {TEXT}; padding: 4px 10px; min-height: 0; box-shadow: none; }}
popover.spark-pop button.spark-item:hover {{ background: {HOVER}; }}
popover.spark-pop button.spark-item:disabled {{ color: {DIM}; }}
separator {{ background: {LINE}; min-height: 1px; margin: 3px 0; }}
.spark-card {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 3px;
  box-shadow: 3px 0 0 {CH_A}, -3px 0 0 {CH_B}; padding: 10px 12px; }}
.spark-card.critical {{ border-color: {PINK}; }}
.spark-card .title {{ font-weight: bold; color: {TEXT}; font-size: 10pt; }}
.spark-card .body {{ color: {MUTED}; font-size: 9pt; }}
.spark-card .app {{ color: {DIM}; font-size: 8pt; font-weight: bold; letter-spacing: 1px; }}
.spark-launcher {{ background: {BG}; border: 1px solid {LINE2}; border-radius: 3px;
  box-shadow: 4px 0 0 {CH_A}, -4px 0 0 {CH_B}; }}
.spark-launcher entry {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {LINE};
  border-radius: 3px; padding: 8px 10px; font-size: 11pt; min-height: 0; box-shadow: none; }}
.spark-launcher entry:focus-within {{ border-color: {ACCENT}; }}
button.spark-app {{ background: transparent; border: 1px solid transparent; border-radius: 3px;
  padding: 6px; color: {TEXT}; box-shadow: none; min-height: 0; }}
button.spark-app:hover, button.spark-app:focus {{ background: {HOVER}; border-color: {LINE2}; }}
button.spark-app.selected {{ background: {HOVER}; border-color: {ACCENT}; }}
.spark-answer {{ color: {ACCENT}; font-size: 18pt; font-weight: bold; }}
.spark-osd {{ background: {BG}; border: 1px solid {LINE2}; border-radius: 3px; padding: 12px 18px;
  box-shadow: 4px 0 0 {CH_A}, -4px 0 0 {CH_B}; }}
.spark-osd progressbar trough {{ background: {PANEL2}; min-height: 6px; border-radius: 0; }}
.spark-osd progressbar progress {{ background: {ACCENT}; min-height: 6px; border-radius: 0; }}
.spark-osd.muted progressbar progress {{ background: {PINK}; }}
.spark-glitch {{ text-shadow: 2px 0 {CH_A}, -2px 0 {CH_B}; }}
list, listview {{ background: transparent; color: {TEXT}; }}
row {{ background: transparent; color: {TEXT}; border-radius: 3px; }}
row:hover {{ background: {HOVER}; }}
row:selected, row:focus {{ background: {HOVER}; box-shadow: 2px 0 0 {CH_A}, -2px 0 0 {CH_B}; }}
scrolledwindow {{ background: transparent; border: none; }}
calendar {{ background: {PANEL}; color: {TEXT}; border: none; }}
calendar:selected {{ background: {ACCENT}; color: {ON_ACCENT}; }}
switch {{ background: {PANEL2}; border: 1px solid {LINE}; border-radius: 3px; }}
switch:checked {{ background: {ACCENT}; }}
switch slider {{ background: {TEXT}; border-radius: 2px; }}
"""
