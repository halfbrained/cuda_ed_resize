import os
from cudatext import *

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'plugins.ini')

option_minimize_xy = 'y' # x,y,xy

''' file:///install.inf

#TODO resize in 'try' - revert changes if error  (... need resize function to revert ...)
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
        option_minimize_xy = ini_read(fn_config, 'editors_resizer', 'minimize_preference', option_minimize_xy)

        self._last_config = None
        # try loading saved state
        state = ini_read(fn_config, 'editors_resizer', '_state', 'non')
        if state != 'non':
            ini_write(fn_config, 'editors_resizer', '_state', 'non')
            
            last_grouping, active_group, ratios = state.split(';')
            ratios = ratios.split('|')
            self._last_config = (int(last_grouping), int(active_group), [float(r) for r in ratios])
        
    def config(self):
        ini_write(fn_config, 'editors_resizer', 'minimize_preference', option_minimize_xy)
        file_open(fn_config)
        
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
        
        #pass; print(f'MIN: Grouping:{grouping}')

        if self.try_revert(grouping, minimizing=True):
            return
        
        if grouping == GROUPS_ONE:
            return
        
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
                
        #pass; print(f'  ** resizes:{resizes}')
        
        edi = ed.get_prop(PROP_INDEX_GROUP)
        self._last_config = (grouping, edi, self._get_splitters_ratios())

        ### resizing
        if len(resizes) == 1:
            r = resizes[0]
            spl_id,newpos = self._get_resize_pos(layout, x, y, r)
            self.set_splitters_pos(grouping, (spl_id,newpos))
            
        elif len(resizes) == 2:
            r0,r1 = resizes
            if r0[0] != r1[0]: # x,y - corner
                ra = r0  if 'x' in option_minimize_xy else  r1
                rb = r1  if 'x' in option_minimize_xy and 'y' in option_minimize_xy else  None
                
                spl_id,newpos = self._get_resize_pos(layout, x, y, ra)
                newpositions = [(spl_id,newpos)]
                if rb:
                    spl_id,newpos = self._get_resize_pos(layout, x, y, rb)
                    newpositions.append((spl_id,newpos))
                self.set_splitters_pos(grouping, *newpositions)
                    
            else: # collapse - editor between others 
                dirs0,dirs1 = ((-1,0),(1,0))  if r0[0] == 'x' else  ((0,-1),(0,+1))
                spl0x,spl0y = self._get_layout_splitters(layout, x, y, *dirs0)
                spl1x,spl1y = self._get_layout_splitters(layout, x, y, *dirs1)
                
                spl0 = layout[spl0x][spl0y]
                spl1 = layout[spl1x][spl1y]

                _isvert, _isvis, pos0, _size = app_proc(PROC_SPLITTER_GET, spl0)
                _isvert, _isvis, pos1, _size = app_proc(PROC_SPLITTER_GET, spl1)
                
                newpos = int((pos0+pos1)*0.5)
                #for i in range(5):
                self.set_splitters_pos(grouping, (spl0, newpos-1), (spl1, newpos+1))
                
        # switch to largest editor
        timer_proc(TIMER_START_ONE, self.focus_biggest_editor, 200)
        
    def set_splitters_pos(self, grouping, *args):
        """args: (splitter_id, pos), (...), ...
        """
        spls = [*args]

        target_splitters = {spl_id for spl_id,pos in spls}
        # get current positions
        for spl_id in SPLITTERS:
            if spl_id not in target_splitters:
                _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_id)
                if spl_id in LAYOUT_SPLITTERS[grouping]:
                    spls.append((spl_id, pos))
                
        # move splitter to start
        for spl_id,_pos in spls:
            app_proc(PROC_SPLITTER_SET, (spl_id, 0)) 
            
        spls.sort()   # now haw all splitters in order
        #pass; print(f' applying spliters : {spls}')
        
        for spl_id,pos in spls:
            app_proc(PROC_SPLITTER_SET, (spl_id, pos)) # move splitter to start
        
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
            
    def load_splitters_ratios(self, grouping, ratios):
        resizes = []
        for spl_id,ratio in zip(SPLITTERS, ratios):
            _isvert, _isvis, _pos, size = app_proc(PROC_SPLITTER_GET, spl_id)
            
            if spl_id in LAYOUT_SPLITTERS[grouping]:
                newpos = int(size*ratio)
                resizes.append((spl_id, newpos))
        self.set_splitters_pos(grouping, *resizes)
        
    def focus_biggest_editor(self, tag=None):
        biggest_area = 0
        biggest_ed = None
        for h in ed_handles():
            e = Editor(h)
            area = e.get_prop(PROP_VISIBLE_LINES) * e.get_prop(PROP_VISIBLE_COLUMNS)

            if area > biggest_area:
                biggest_area = area
                biggest_ed = e
                
        if biggest_ed:
            biggest_ed.focus()
        
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
            
    def _get_resize_pos(self, layout, x, y, r):
        splx,sply = (-r[1],0)  if r[0] == 'x' else  (0,-r[1])
        spl_id = layout[x+splx][y+sply]
        _isvert, _isvis, _pos, size = app_proc(PROC_SPLITTER_GET, spl_id)
            
        newpos = size  if r[1] > 0 else  0
        return spl_id, newpos

    def _get_splitters_ratios(self):
        res = []
        for spl_id in SPLITTERS:
            _isvert, _isvis, pos, size = app_proc(PROC_SPLITTER_GET, spl_id)
            res.append(pos/size)
        return res
        

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
    
