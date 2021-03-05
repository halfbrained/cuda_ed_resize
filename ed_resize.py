import os
from cudatext import *

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'plugins.ini')

option_minimize_xy = 'y' # x,y,xy
option_min_focus = 1 # 0=stay, 1=go to last used

''' file:///install.inf
'''

SPLITTERS = [
    SPLITTER_G1,
    SPLITTER_G2,
    SPLITTER_G3,
    SPLITTER_G4,
    SPLITTER_G5,
]

class Command:

    def __init__(self):
        global option_minimize_xy
        global option_min_focus

        option_minimize_xy = ini_read(fn_config, 'editors_resizer', 'minimize_preference', option_minimize_xy)
        option_min_focus = int(ini_read(fn_config, 'editors_resizer', 'min_focus', str(option_min_focus)))

        self.group_ratios = {} # (rx,ry,grouping)

        self._last_config = None
        # try loading saved state
        state = ini_read(fn_config, 'editors_resizer', '_state', 'non')
        if state != 'non':
            ini_write(fn_config, 'editors_resizer', '_state', 'non')

            last_grouping, active_group, ratios = state.split(';')
            ratios = ratios.split('|')
            self._last_config = (int(last_grouping), int(active_group), [float(r) for r in ratios])

    def config(self):
        ini_write(fn_config, 'editors_resizer', 'minimize_preference',  option_minimize_xy)
        ini_write(fn_config, 'editors_resizer', 'min_focus',            str(option_min_focus))
        file_open(fn_config)

    def on_focus(self, ed_self):
        group = ed.get_prop(PROP_INDEX_GROUP)
        self.unmin_group(group)

    def on_exit(self, ed_self):
        # keep minimized/maximized state after restart
        if self._last_config:
            last_grouping, active_group, splitters = self._last_config
            ratios = '|'.join(['{:.3}'.format(r) for r in splitters])
            s = '{};{};{}'.format(last_grouping, active_group, ratios)
            ini_write(fn_config, 'editors_resizer', '_state', s)

    def tgl_max(self):
        grouping = app_proc(PROC_GET_GROUPING, '')

        #pass; print(f'MAX: Grouping:{grouping}')

        if self.try_revert(grouping, minimizing=False):
            return

        if grouping == GROUPS_ONE:
            return

        layout = LAYOUTS[grouping]

        edi = ed.get_prop(PROP_INDEX_GROUP)
        edis = 'e'+str(edi)

        lw = len(layout)
        lh = len(layout[0])
        edcells = self._get_ed_layout_cells(layout, edis)
        x,y = edcells[0]

        spl_poss = []
        for i in range(lw):
            for j in range(lh):
                item = layout[i][j]
                if type(item) != int: # not splitter - skip
                    continue
                if x != i  and  j != y: # not on editor axis - skip
                    continue

                spl_id = item
                if i < x  or  j < y: 
                    spl_poss.append((spl_id, 0))
                else: 
                    _isvert, _isvis, _pos, size = app_proc(PROC_SPLITTER_GET, spl_id)
                    if spl_id in LAYOUT_SPLITTERS[grouping]:
                        spl_poss.append((spl_id, size))

        #pass; print(f' + MAX:spl poss: {spl_poss}')

        # save for try_revert
        self._last_config = (grouping, edi, self._get_splitters_ratios())

        self.set_splitters_pos(grouping, *spl_poss)

    def tgl_min(self):
        grouping = app_proc(PROC_GET_GROUPING, '')
        if grouping == GROUPS_ONE:
            return

        edi = ed.get_prop(PROP_INDEX_GROUP)
        if self.unmin_group(edi):
            return

        #pass; print(f'MIN: Grouping:{grouping}')

        layout = LAYOUTS[grouping]

        x,y, resizes = self._prepare_resizes(layout)
        nres = len(resizes)

        # check if corner on T-intersec
        if len(resizes) == 2:
            r0,r1 = resizes

            dirx = -r0[1]
            diry = -r1[1]
            dirx = 1 if dirx > 0 else -1
            diry = 1 if diry > 0 else -1
            splx,sply = self._get_layout_splitters(layout, x, y, dirx, diry)

            if resizes[0][0] != resizes[1][0]:
                if type(layout[splx][sply+diry]) == str: # found editor - T intersec
                    resizes = [r0] # x resize

                elif type(layout[splx+dirx][sply]) == str:
                    resizes = [r1] # y resize

        #self._last_config = (grouping, edi, self._get_splitters_ratios())

        if len(resizes) == 2:
            r0,r1 = resizes
            if r0[0] != r1[0]: # x,y - corner
                resizes = [r for r in resizes if r[0] in option_minimize_xy]
            else:
                resizes = [resizes[0]]

        self.save_group_ratios(layout, x, y, edi, grouping)

        for r in resizes:
            ax = r[0]
            _size, items = self._get_ax_layout(ax, layout, x, y, minimized_group=edi)
            self.set_splitters_pos(grouping, *items)

        if option_min_focus == 1:
            self.focus_last_ed(layout)

    def unmin_group(self, group):
        grouping = app_proc(PROC_GET_GROUPING, '')
        if grouping == GROUPS_ONE:
            return
            
        layout = LAYOUTS[grouping]

        edt = ed_group(group) #TODO can be none?
        rx,ry,saved_grouping = self.group_ratios.get(group, (None, None, None))
        edis = 'e'+str(group)

        if saved_grouping != grouping:
            rx,ry = 1,1

        cells = self._get_ed_layout_cells(layout, 'e'+str(group))
        x,y = cells[0]  # first active ed group:  0,0 - top left

        (w,spl_w),(h,spl_h) = self._get_ed_size('x', layout, x, y), self._get_ed_size('y', layout, x, y)

        def unmin_ax(ax, ratio, ed_size): #SKIP
            if ed_size < 0:
                return False

            #  size, before:[(ed_ind, spl_id, pos)],  after:[...]
            size, items = self._get_ax_layout(ax, layout, x, y)

            if ed_size < 20  and  size != -1: # expand horizontally
                ratio = ratio or 1

                prev_pos = 0
                groups_widths = []
                spl_w = 0
                for ed_s, spl_id, pos in items:
                    groups_widths.append(pos - prev_pos - spl_w)
                    prev_pos = pos
                    spl_w = 4
                groups_widths.append(size - prev_pos - 4)
                opened_group_widths = [gsize for gsize in groups_widths  if gsize > 20]

                #average_width = sum(groups_widths) / len(groups_widths)
                new_average_width = sum(opened_group_widths) / (len(opened_group_widths) + 1)

                new_gr_size = int(ratio*new_average_width)

                spl_poss = []
                prev_old = 0
                prev_new = 0
                spl_w = 0
                for ed_s, spl_id, pos in items:
                    prev_new += 4  if prev_new > 0 else  0 # 4=splitter width

                    if ed_s == edis:
                        newpos = int(prev_new + new_gr_size)
                    else:
                        #newpos = int(prev_new + (pos - prev_old)*(1 - ratio))
                        prev_ratio = (pos - prev_old - spl_w)/(sum(opened_group_widths))
                        space_left = (sum(opened_group_widths)+10 - new_gr_size)
                        newpos = int(prev_new + space_left*prev_ratio + 1)

                    spl_poss.append((spl_id, newpos))
                    prev_old = pos
                    prev_new = newpos
                    spl_w = 4

                self.set_splitters_pos(grouping, *spl_poss)
                return True

            return False

        done_x = unmin_ax('x', ratio=rx, ed_size=w)
        done_y = unmin_ax('y', ratio=ry, ed_size=h)
        return done_x or done_y

    def reset_sizes(self):
        grouping = app_proc(PROC_GET_GROUPING, '')
        if grouping == GROUPS_ONE:
            return

        layout = LAYOUTS[grouping]
        lw = len(layout)
        lh = len(layout[0])

        spls_info = {}
        for spl_id in SPLITTERS:
            info = app_proc(PROC_SPLITTER_GET, spl_id)
            _isvert, isvis, _pos, _size = info

            if isvis: 
                spls_info[spl_id] = info

        resizes = []
        for x in range(lw):
            for y in range(lh):
                spl_id = layout[x][y]
                if type(spl_id) == int  and  spl_id in spls_info: 
                    isvert, _isvis, pos, size = spls_info[spl_id]
                    del spls_info[spl_id]

                    lcount = lw  if isvert else  lh
                    lpos = x  if isvert else  y
                    edsize = size/((lcount+1)/2)
                    newpos = edsize * ((lpos+1)/2)
                    resizes.append((spl_id, int(newpos)))

        self.set_splitters_pos(grouping, *resizes)

    def try_revert(self, grouping, minimizing):
        if self._last_config is not None:
            last_grouping, active_group, splitters = self._last_config
            self._last_config = None

            if grouping == last_grouping:
                self._dbg_last_config = self._last_config
                self.load_splitters_ratios(grouping, splitters)

                # focus previous focussed group
                if minimizing:
                    e = ed_group(active_group)
                    if e:
                        e.focus()
                return True

    def save_group_ratios(self, layout, x, y, edi, grouping):
        rx = self._get_group_ratio('x', layout, x, y)
        ry = self._get_group_ratio('y', layout, x, y)

        self.group_ratios[edi] = (rx,ry,grouping)

    def set_splitters_pos(self, grouping, *args):
        """args: (splitter_id, pos), (...), ...
        """
        spls = [*args]
        main_isvert, _isvis, _pos, msize = app_proc(PROC_SPLITTER_GET, spls[0][0])

        target_splitters = {spl_id for spl_id,pos in spls}
        # get current positions
        for spl_id in SPLITTERS:
            if spl_id not in target_splitters   and   spl_id in LAYOUT_SPLITTERS[grouping]:
                    isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_id)
                    if main_isvert == isvert:
                        spls.append((spl_id, pos))

        # move splitter to start
        for spl_id,_pos in spls:
            app_proc(PROC_SPLITTER_SET, (spl_id, 0))

        spls.sort()   # now haw all splitters in order

        # compress rightmost minimized
        prev_pos = msize
        prev_new = msize
        for i in range(len(spls)-1,-1,-1):
            spl_id,pos = spls[i]
            if prev_pos - pos > 30:
                break

            spls[i] = (spl_id, prev_new-10)
            prev_pos = pos
            prev_new = prev_new-10

        for spl_id,pos in spls:
            app_proc(PROC_SPLITTER_SET, (spl_id, pos)) # move splitter to start

        #pass; print(f'>>> applying spliters : {spls}')

    def load_splitters_ratios(self, grouping, ratios):
        resizes = []
        for spl_id,ratio in zip(SPLITTERS, ratios):
            _isvert, _isvis, _pos, size = app_proc(PROC_SPLITTER_GET, spl_id)

            if spl_id in LAYOUT_SPLITTERS[grouping]:
                newpos = int(size*ratio)
                resizes.append((spl_id, newpos))
        self.set_splitters_pos(grouping, *resizes)

    def focus_last_ed(self, layout):
        timed_eds = []
        for i in range(6):
            ed = ed_group(i) 
            if ed is not None:
                timed_eds.append((ed.get_prop(PROP_ACTIVATION_TIME), ed, i))

        timed_eds.sort(key=lambda item: item[0], reverse=True)
        for _time, ed, group in timed_eds:
            cells = self._get_ed_layout_cells(layout, 'e'+str(group))
            x,y = cells[0]  # first active ed group:  0,0 - top left
            (w,spl_w),(h,spl_h) = self._get_ed_size('x', layout, x, y), self._get_ed_size('y', layout, x, y)

            if (w == -1 or w > 20) and (h == -1 or h > 20):
                ed.focus()

    def _get_ax_layout(self, ax, layout, x, y, minimized_group=None):

        if ax == 'x':
            vec = [layout[i][y] for i in range(len(layout))]
            vecpos = x
        else:
            vec = layout[x]
            vecpos = y

        if len(vec) == 1: # one high/wide - cant un-min
            return -1, None #TODO handle

        res = []
        for ed,spl in zip(vec[::2], vec[1::2]):
            if spl is not None:
                _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl)
            else: # last
                pos = size
            res.append((ed, spl, pos))

        if minimized_group is not None:
            work = [*res]
            res.clear()
            min_edis = 'e'+str(minimized_group)

            # find current size of minimizeable group
            gr_size = -1
            min_total_size = 0
            prev_pos = 0
            spl_w = 0
            for gr_edis,spl,pos in work:
                if gr_edis == min_edis:
                    gr_size = pos - prev_pos - spl_w
                if pos - prev_pos <= 20:
                    min_total_size += pos - prev_pos - spl_w
                prev_pos = pos
                spl_w = 4

            if gr_size == -1:
                gr_size = size - prev_pos - spl_w
            if size - prev_pos <= 20:
                min_total_size += size - prev_pos - spl_w

            worksize = size - min_total_size - 4*len(work)
            prev_new = 0
            prev_old = 0
            spl_w = 0
            for gr_edis,spl,pos in work:
                if gr_edis == min_edis: # minimizeable group
                    newpos = round(prev_new + 10) #TODO proper minimized group size?
                else: # other groups
                    edt = ed_group(int(gr_edis[1:]))
                    #axsize = self._get_ed_size(edt, ax)
                    axsize = pos - prev_old - spl_w
                    ratio = axsize/(worksize-(gr_size-10))

                    if axsize > 20: # not minimized
                        newpos = round(prev_new + (pos - prev_old + (gr_size-10)*ratio))
                    else: # minimized - keep size
                        newpos = round(prev_new + (pos - prev_old))
                res.append((spl,newpos)) # different format

                prev_new = newpos
                prev_old = pos
                spl_w = 4

        return size, res

    def _get_next_spls(self, ax, layout, x, y):
        if ax == 'x': # row
            before = [layout[i][y] for i in range(x)  if type(layout[i][y]) == int]
            after = [layout[i][y] for i in range(x, len(layout)) if type(layout[i][y]) == int]
        else: # column
            before = [spl for spl in layout[x][:y]  if type(spl) == int]
            after = [spl for spl in layout[x][y:]  if type(spl) == int]

        return before,after

    def _get_group_ratio(self, ax, layout, x, y):
        spl_before, spl_after = self._get_next_spls(ax, layout, x, y)

        if not spl_before and not spl_after: # one editor high|wide layyuyt
            return -1

        prev_pos = 0
        groups_widths = []
        for spl in spl_before+spl_after:
            #prev_pos += 4  if prev_pos > 0 else  0

            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl)
            if pos - prev_pos > 20:
                groups_widths.append(pos - prev_pos)
            prev_pos = pos
        #prev_pos += 4
        if size - prev_pos > 20: 
            groups_widths.append(size - prev_pos)

        if spl_before:
            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_before[-1])
            start = pos
        else:
            start = 0

        if spl_after:
            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_after[0])
            end = pos
        else:
            end = size

        #return (end-start)/size # percent of layout

        average_width = sum(groups_widths) / len(groups_widths)
        r = (end-start) / average_width
        commons = [1, 5/6, 0.75, 0.5]
        for common in commons:
            delta = abs(r-common)
            if delta < common*0.04:
                r = common
                break
        return r # percent above 'average''

    def _prepare_resizes(self, layout):
        edi = ed.get_prop(PROP_INDEX_GROUP)
        edis = 'e'+str(edi)

        lw = len(layout)
        lh = len(layout[0])
        cells = self._get_ed_layout_cells(layout, edis)

        x,y = cells[0]  # first active ed group:  0,0 - top left
        edw = len([True for i in range(x,lw)  if layout[i][y] == edis])
        edh = len([True for i in range(y,lh)  if layout[x][i] == edis])

        is_edge_l = x == 0
        is_edge_t = y == 0
        is_edge_r = x + edw == lw
        is_edge_b = y + edh == lh
        edgen = sum((is_edge_l, is_edge_t, is_edge_r, is_edge_b))
        iscorner = edgen == 2 and (is_edge_t != is_edge_b  and  is_edge_l != is_edge_r)

        resizes = [] # ('x'|'y', direction <-1, -0.5, +0.5, +1>)
        # corner - (is corner, 2 edges)                -- check if T-intersection | decide option        :: xy
        # between other in one row - 0.5 (not corner, 2 edges)  --  collapse sides  :: xx|yy
        # side no corner - (not corner, 1 edge)     -- collapse to side     :: x|y
        # side 2 corners - (not corner, 3 edges)    -- collapse to side     :: x|y
        if iscorner:
            if is_edge_t: resizes.append(('y', -1))
            if is_edge_b: resizes.append(('y', +1))
            if is_edge_l: resizes.append(('x', -1))
            if is_edge_r: resizes.append(('x', +1))
        else:
            if edgen == 2: # between others
                if lh == 1:
                    resizes = [('x', +0.5), ('x', -0.5)]
                else:
                    resizes = [('y', +0.5), ('y', -0.5)]
            else: # 1 or 3 edges
                if is_edge_t and (edgen == 1 or is_edge_l == is_edge_r): resizes.append(('y', -1))
                if is_edge_b and (edgen == 1 or is_edge_l == is_edge_r): resizes.append(('y', +1))
                if is_edge_l and (edgen == 1 or is_edge_t == is_edge_b): resizes.append(('x', -1))
                if is_edge_r and (edgen == 1 or is_edge_t == is_edge_b): resizes.append(('x', +1))

        resizes.sort()

        return x,y, resizes

    def _get_ed_layout_cells(self, layout, edis):
        lw = len(layout)
        lh = len(layout[0])
        cells = []
        for x in range(lw):
            for y in range(lh):
                if layout[x][y] == edis:
                    cells.append((x,y))
        return cells

    def _get_layout_splitters(self, layout, x, y, dirx, diry):
        lw = len(layout)
        lh = len(layout[0])

        splx = 0
        sply = 0
        if dirx != 0:
            for i in range(1,lw):
                if type(layout[x+dirx*i][y]) == int: # found splitter
                    splx = x+dirx*i
                    break
        if diry != 0:
            for i in range(1,lh):
                if type(layout[x][y+diry*i]) == int: # found splitter
                    sply = y+diry*i
                    break
        return splx, sply

    def _get_splitters_ratios(self):
        res = []
        for spl_id in SPLITTERS:
            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_id)
            res.append(pos/size)
        return res

    #def _get_ed_size(self, ed, ax):
        #l,t,r,b = ed.get_prop(PROP_COORDS)
        #return r-l  if ax == 'x' else  b-t
    def _get_ed_size(self, ax, layout, x, y):
        spl_before, spl_after = self._get_next_spls(ax, layout, x, y)

        if not spl_before and not spl_after: # one editor high|wide layyuyt
            return -1,-1

        prev_pos = 0
        for spl in spl_before+spl_after:
            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl)
            prev_pos = pos

        if spl_before:
            spl_w = 4
            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_before[-1])
            start = pos
        else:
            spl_w = 0
            start = 0

        if spl_after:
            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_after[0])
            end = pos
        else:
            end = size
        return end-start, spl_w

# [y][x] - convenient format to write, rotated to [x][y] next
LAYOUTS = { # grouping -> layout
    GROUPS_2VERT: [ ['e0', SPLITTER_G1, 'e1']],

    GROUPS_2HORZ: [ ['e0'], 
                    [SPLITTER_G1], 
                    ['e1']],

    GROUPS_3VERT: [ ['e0', SPLITTER_G1, 'e1', SPLITTER_G2, 'e2']],

    GROUPS_3HORZ: [ ['e0'], 
                    [SPLITTER_G1], 
                    ['e1'], 
                    [SPLITTER_G2], 
                    ['e2']],

    GROUPS_1P2VERT:[['e0', SPLITTER_G3, 'e1'],
                    ['e0', SPLITTER_G3, SPLITTER_G2],
                    ['e0', SPLITTER_G3, 'e2']],

    GROUPS_1P2HORZ:[['e0',          'e0',           'e0'],
                    [SPLITTER_G3,   SPLITTER_G3,    SPLITTER_G3],
                    ['e1',          SPLITTER_G2,    'e2']],

    GROUPS_4VERT: [ ['e0', SPLITTER_G1, 'e1', SPLITTER_G2, 'e2', SPLITTER_G3, 'e3']],

    GROUPS_4HORZ: [ ['e0'], 
                    [SPLITTER_G1], 
                    ['e1'], 
                    [SPLITTER_G2], 
                    ['e2'],
                    [SPLITTER_G3], 
                    ['e3']],

    GROUPS_4GRID: [ ['e0',          SPLITTER_G1, 'e1'], 
                    [SPLITTER_G3,   SPLITTER_G3, SPLITTER_G3], 
                    ['e2',          SPLITTER_G1, 'e3']],
                    #['e2',          SPLITTER_G2, 'e3']], - G2 follows G1, so no need for it

    GROUPS_6VERT: [ ['e0', SPLITTER_G1, 'e1', SPLITTER_G2, 'e2', SPLITTER_G3, 'e3', SPLITTER_G4, 'e4', SPLITTER_G5, 'e5']],

    GROUPS_6HORZ: [ ['e0'], 
                    [SPLITTER_G1], 
                    ['e1'], 
                    [SPLITTER_G2], 
                    ['e2'],
                    [SPLITTER_G3], 
                    ['e3'],
                    [SPLITTER_G4], 
                    ['e4'],
                    [SPLITTER_G5], 
                    ['e5']],

    GROUPS_6GRID: [ ['e0',          SPLITTER_G1, 'e1',          SPLITTER_G2, 'e2'], 
                    [SPLITTER_G3,   SPLITTER_G3, SPLITTER_G3,   SPLITTER_G3, SPLITTER_G3], 
                    ['e3',          SPLITTER_G1, 'e4',          SPLITTER_G2, 'e5']],
}

# set() of visible splitters for layouts; splitter's 'is_visible' property is problematic for this 
LAYOUT_SPLITTERS = {} 

# transposing from [y][x] to [x][y]
for l in LAYOUTS.values():
    w = len(l) # h in new
    h = len(l[0]) # w in new
    copy = [*l]
    l.clear()
    for y in range(h): # new w -- x
        l.append([copy[x][y]  for x in range(w)]) # new columns

# fill LAYOUT_SPLITTERS
for grouping,layout in LAYOUTS.items():
    splitters = set()
    for column in layout:
        for item in column:
            if type(item) == int:
                splitters.add(item)
    
    LAYOUT_SPLITTERS[grouping] = splitters