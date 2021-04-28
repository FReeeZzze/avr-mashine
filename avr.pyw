#coding: utf8
##-- lab work with Atmega8  A.B.Glazov
##-- AVRLAB104 ver 1.03 for python 3.4
##-- added
##--     address ADC
##--     commands: in PIND(iAAAA), out PORTB(oAAAA),
##--               store byte(zAAAA), copy byte(yAAAA)


import time
import serial
import threading
from time import *

#-- общие ресурсы

##== COM порт
#port = 'COM5'
#port = 'COM3'
port = 'COM1'

##== искать иаксимальный порт если он не задан
if port == "":
    ports = []
    for port_num in range(0,10):
        port = 'COM'+str(port_num)
        try:
            ser = serial.Serial(port, 9600, timeout=0.2)
            ports.append(port)
            ser.close()
        except:
            pass
    port = ports[-1].strip()

ser = serial.Serial(port, 9600, timeout=0.2)
busy_ser = 0

##== очередь для приема сообщений и флаг ее занятости
lst_in = []
busy_in = 0

##== очередь отправки сообщений и признак ее занятости
lst_out =[]
busy_out = 0

##== глобальные переменные
main_tau = 10       #- период главного цикла в миллисекундах
flg_execute = 0     #- признак непрерывности выполнения программы(0 - нет, 1 - до пустой команды, 2 - в цикле)
step_tau = 500      #- длительность шага в миллисекундах
mstep_num = 0       #- номер миллишага в шаге
mstep_count = step_tau/main_tau     #- число миллишагов в шаге
row_count = 10      #- высота списков с командами


############################ socketio server #############################
from flask import Flask, render_template
import socketio
sio = socketio.Server(async_mode='threading', cors_allowed_origins='*', logger=True)
app = Flask(__name__)
app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

# работающий пользователь
workingUser = ''
# список всех подключенных пользователей
connectedUsers = []

# event клика
event_click = '<Button-1>'

@app.route('/')
def index():
    return 'hello'
# функция обертка над функциями вызова цикла
# 'loop' - функция
# 'data' - лист
def loop_wrapper(loop, data):
    global step_tau
    global event_click
    # устанавливаем шаг
    step_tau = data["step"]
    edt_step.set(data["step"])
    # устанавливаем комманды
    for command in data["commands"]:
        lbx_prog.append(command["name"])
    loop(event_click)

def authenticate_user(environ):
    global workingUser
    username = environ['HTTP_USER_AGENT']
    connectedUsers.append(username)
    if not workingUser:
        workingUser = username
    return username

def isAuth(sid):
    session = sio.get_session(sid)
    return workingUser == session['username']

def authMessage(sid):
    session = sio.get_session(sid)
    if workingUser == session['username']:
        sio.emit('auth', { 'status': 'authorized', 'message': 'you can start working' }, room=sid)
    else:
        sio.emit('auth', { 'status': 'waiting', 'message': 'wait your turn' }, room=sid)

# event с названием 'connect'
@sio.event
def connect(sid, environ):
    username = authenticate_user(environ)
    sio.save_session(sid, {'username': username})
    authMessage(sid)
    print('connect', sid)

# event с названием 'loop_begin'
# используется для команды 'СТАРТ', чтобы начать цикл бесконечный цикл
@sio.event
def loop_begin(sid, data):
    if isAuth(sid):
        # очищаем чтобы вставить наши комманды
        fnc_clearlstout(event_click)
        # запускаем цикл
        loop_wrapper(fnc_loop, data)
    else:
        authMessage(sid)

# event с названием 'start_loop',
# используется для команды 'СТАРТ', чтобы начать цикл 1 раз
@sio.event
def start_loop(sid, data):
    if isAuth(sid):
        # очищаем чтобы вставить наши комманды
        fnc_clearlstout(event_click)
        # запускаем цикл
        loop_wrapper(fnc_start, data)
        # устанавливаем индекс
        lbx_prog.set_index(int(data["index"]))
    else:
    	authMessage(sid)

@sio.event
def execute(sid, data):
    if isAuth(sid):
        # очищаем чтобы вставить наши комманды
        fnc_clearlstout(event_click)
        # запускаем цикл
        lbx_prog.set_index(int(data["index"]))
        loop_wrapper(fnc_step, data)
        sio.emit('result', { 'status': 'ok', 'cancel': True })
    else:
        authMessage(sid)

# event с названием 'stop_loop'
# используется чтобы отсановить цикл
@sio.event
def stop_loop(sid):
    if isAuth(sid):
        fnc_stop(event_click)
        sio.emit('result', { 'status': 'ok' })
    else:
        authMessage(sid)

# event с названием 'send_data'
# используется чтобы передать сообщение (пример: 'b0200ff')
# и получения ответа (пример: 'Ok')
@sio.event
def send_data(sid, message):
    if isAuth(sid):
        edt_strout.set(message)
        fnc_sendstrout(event_click)
    else:
        authMessage(sid)

# event с названием 'disconnect'
@sio.event
def disconnect(sid):
    global workingUser
    session = sio.get_session(sid)
    connectedUsers.remove(session['username'])
    if not len(connectedUsers):
        workingUser = ''
    else:
        workingUser = connectedUsers[0]
    authMessage(sid)
    #показывает SID пользователя который отключился от socket server
    print('disconnect', sid)

# 192.168.1.115 test home ip
SERVER_IP_ADDR = '127.0.0.1'
appSocket = threading.Thread( target = app.run, args = [SERVER_IP_ADDR, 5000])
appSocket.daemon = True
###########################################################################


#-- потоки отправки отправки и приема сообщений
##== функция отправки сообщений
def work_out():
    global lst_out
    global busy_out
    global ser
    global busy_ser
    while True:
        #if busy_out != 0 : print busy_out
        if len(lst_out) > 0  and not busy_out and not busy_ser:
            busy_ser = 2
            busy_out = 2
            str_out = lst_out.pop(0)
            busy_out = 0
            str_out += "\n"
            ser.write( str_out.encode() )
            busy_ser = 0
            #print ("out: ", str_out)
        sleep(0.001)

##== поток отправки сообщений
tr_out = threading.Thread( target = work_out)
tr_out.daemon = True
tr_out.start()

##== функция приема сообщений
def work_in():
    global lst_in
    global busy_in
    global ser
    global busy_ser
    while True:
        if not busy_ser:
            busy_ser = 1
            str_in = ser.readline()
            busy_ser = 0

            if len(str_in) > 0:
                while busy_in:
                    sleep(0.001)
                busy_in = 1
                str_in = str_in.strip()
                sio.emit('result', { 'message': str_in.decode("UTF8") })
                lst_in.append(str_in.decode("UTF8"))
                busy_in = 0
                #print ("in: ", str_in.decode("UTF8"))
        sleep(0.001)

##== поток приема сообщений
tr_in = threading.Thread( target = work_in)
tr_in.daemon = True
tr_in.start()

#-- подключить графические библиотеки
# from Tkinter import *
# import ttk
# from tkFont import Font
# import tkFileDialog
from tkinter import *
from tkinter import filedialog
from tkinter import font
from tkinter import ttk



#-- упрощенные классы виджетов

##-- кнопка с наборои параметров
class Buttongrid(  ttk.Button):
    def __init__( self, panel, row_num, col_num, btn_text, btn_width = 10, btn_fnc = ""):
        ttk.Button.__init__(self, panel, text = btn_text, width = btn_width)
        self.grid(row = row_num, column = col_num, sticky=E+N, pady = 5 , padx = 5)
        if btn_fnc != "":
            self.bind("<Button-1>", btn_fnc)

##-- поле ввода с меткой
class Labelentry(ttk.Entry):
    def __init__( self, panel, row_num, col_num, lab_text = "",
                ent_width = 10,  init_val = "",
                fnc_return = "", col_span = 1 ):
        self.var = StringVar()
        ttk.Entry.__init__( self, panel,  width = ent_width, textvariable = self.var, font = dFont)
        self.var.set(init_val)
        if  fnc_return  !=  "":
            self.bind('<Return>', fnc_return)

        if len(lab_text) > 0:
            self.lab = ttk.Label( panel, text=lab_text , font = dFont )
            self.lab.grid( row = row_num, column = col_num, sticky = E , padx = 5)
        self.grid(row = row_num, column = col_num + 1, columnspan = col_span, sticky=W, pady = 5, padx=5 )

    def  get(self):
        return  self.var.get()

    def  set( self, new_text ):
        self.var.set(new_text)

##-- раскрывающийся список с меткой
class Labelcombobox(ttk.Combobox):
    def __init__( self, panel, row_num, col_num, lab_text = "",  cbx_width = 20, cbx_height = 6, lst_values = [1,2,3], fnc_sel = 0, row_span = 1, col_span = 1):
        if len(lab_text) > 0:
            self.lab = ttk.Label( panel, text=lab_text , font = dFont )
            self.lab.grid( row = row_num, column = col_num, sticky = E , padx = 5, columnspan = col_span)

        ttk.Combobox.__init__( self, panel, values = lst_values, height=cbx_height, width = cbx_width, font = dFont)
        self.set(lst_values[0])
        self.grid(row = row_num, column = col_num + 1, sticky = W, pady = 5, padx = 5)
        if fnc_sel != 0:
            self.bind("<<ComboboxSelected>>", fnc_sel)

    def load(self, file_name):
        if len(file_name) >=1:
            self["values"]=[]
            fhn = open(file_name )
            self["values"] = fhn.readlines()
            fhn.close()
            self.set(self["values"][0])


##-- список с меткой
class Labellistbox(Listbox):
    def __init__( self, panel, row_num, col_num, lab_text = "",  lbx_width = 20, lbx_height = 6, lst_values = [1,2,3], fnc_dbl = 0, row_span = 1, col_span = 1):
        self.panel = ttk.Frame(panel )

        Listbox.__init__( self, self.panel, width = lbx_width, height=lbx_height, font = dFont)

        if len(lab_text) > 0:
            self.lab = ttk.Label( panel, text=lab_text , font = dFont )
            self.lab.grid( row = row_num, column = col_num, sticky = W , padx = 5, columnspan = col_span)
        self.panel.grid(row = row_num+1, column = col_num, sticky = W , padx = 5, columnspan = col_span, pady = 5)

        for str_lbx in lst_values:
            Listbox.insert(self, END, str_lbx)

        self.pack(side="left", fill="y")
        self.scbr = Scrollbar(self.panel, orient="vertical")
        self.scbr.pack(side="right", fill="y")

        self.scbr.config(command=self.yview)
        self.config(yscrollcommand=self.scbr.set)

        if fnc_dbl != 0:
            self.bind('<Double-Button-1>', fnc_dbl)

    def  append( self, new_text ):
        Listbox.insert(self, END, new_text )


    def  get(self):
        try:
            return Listbox.get(self, self.curselection()[0])
        except:
            return ""

    def  get_index(self):
        try:
            print(self.curselection())
            return  self.curselection()[0]
        except:
            return -1

    def  set_index(self, index):
        try:
            #self.selection_clear()
            self.select_clear(0, "end")
            self.selection_set( index )
            self.see(index)
            self.activate(index)
            self.selection_anchor(index)
            print('set_index: ' + str(index))
            return index
        except:
            print('err')
            return  -1


    def  clear(self):
        Listbox.delete(self, 0, END)

    def  insert( self, new_text ):
        sel_num = self.get_index()
        if sel_num >= 0:
            Listbox.insert(self, sel_num, new_text )
        else:
            Listbox.insert(self, END, new_text )

    def  delete(self):
        sel_num = self.get_index()
        if sel_num >= 0:
            Listbox.delete( self, sel_num )

    def save(self, file_name):
        if len(file_name) >=1:
            fhn = open(file_name, "w")
            lst = list(Listbox.get(self, 0, END))
            lst.append("")
            fhn.write('\n'.join(lst))
            fhn.close()

    def load(self, file_name):
        if len(file_name) >=1:
            fhn = open(file_name )
            lst_values = fhn.readlines()
            fhn.close()

            Listbox.delete(self, 0, END)
            for str_loc in lst_values:
                Listbox.insert(self, END, str_loc.strip())



#-- нарисовать форму
root = Tk()

#-- настройки оформления
clr_root = '#ff2793'
stl = ttk.Style()
dFont = font.Font(family="helvetica", size=14)
stl.configure('.', font=dFont, background=clr_root, foreground= "black")
stl.configure('TLabel', foreground = 'black', sticky=E,  padx = 10)
stl.configure('TEntry', padx= 5, pady= 5, sticky = W, font=dFont)
stl.configure('TButton', padx= 5, pady= 5, sticky = W, font=dFont)
stl.configure('TCombobox', padx= 5, pady= 5, sticky = W, width = 10, font=dFont)

#-- панель с заголовком
pnl_head = ttk.Frame(root, height = 100)
pnl_head.pack(side = 'top', fill = 'x')

##-- заголовок программы
ttk.Label(pnl_head, text = 'Лабораторный комплекс для работы с микроконтроллером Atmega8' ).pack()
ttk.Label(pnl_head, text = 'версия 1.04    А.Б.Глазов' ).pack()
ttk.Label(pnl_head, text = ' ').pack()


#-- панель для основного содержимого
pnl_main = ttk.Frame(root, height = 800)
pnl_main.pack(side = 'bottom', fill = 'both', expand = 1)

#-- правая панель со списком отправленных строк
pnl_prog = ttk.Frame(pnl_main, width = 200)
pnl_prog.pack(side = 'right', fill = 'y', padx = 20)

##-- листбокс запомненных значений (программа)
hgt_frmlbx = 10

lst_prog = [ 'b01501F','m015008' ]

def fnc_lbxdbl(event):
    edt_strout.set( lbx_prog.get())
    fnc_sendstrout(event)

lbx_prog = Labellistbox( pnl_prog, 0,0, u"список строк:",
    38, row_count, lst_prog, fnc_lbxdbl, hgt_frmlbx, 2 )

##-- кнопка добавления строки в листбокс программы
row_num =1 + hgt_frmlbx
def fnc_addlbxout(event):
    lbx_prog.append( edt_strout.get() )

btn_addlbxout = Buttongrid( pnl_prog, row_num, 0, u'добавить', 10, fnc_addlbxout)

##-- кнопка вставки строки в листбокс программы
def fnc_inslbxout(event):
    lbx_prog.insert( edt_strout.get() )

btn_inslbxout = Buttongrid( pnl_prog, row_num, 1, u'вставить', 10, fnc_inslbxout)

##-- кнопка удаления строки из листбокса программы
row_num = row_num + 1
def fnc_dellstout(event):
    lbx_prog.delete()

btn_dellbxout = Buttongrid( pnl_prog, row_num, 0, u'удалить', 10, fnc_dellstout)

##-- кнопка очистки всех строк листбокса программы
def fnc_clearlstout(event):
    lbx_prog.clear()

btn_clearlbxout = Buttongrid( pnl_prog, row_num, 1, u'очистить', 10, fnc_clearlstout)

##-- кнопка шага для листбокса программы
row_num = row_num+1
def fnc_step(event):
    index = lbx_prog.get_index()
    str_out = lbx_prog.get()
    if  len(str_out) >2:
        print( str_out)
        if str_out[0] != ";":
            print (str_out)
            edt_strout.set( str_out)
            fnc_sendstrout(event)
    index += 1
    lbx_prog.set_index(index)

btn_step = Buttongrid( pnl_prog, row_num, 0, u'выполнить', 10, fnc_step)

##-- поле для длительности шага
row_num += 1

def fnc_setsteptau(event):
    global  mstep_count
    global  step_tau
    step_tau = int(edt_step.get())
    mstep_count = step_tau/main_tau     #- число миллишагов в шаге


edt_step = Labelentry( pnl_prog, row_num, 0, u'шаг( мс ):',10, '500', fnc_setsteptau)

##-- кнопка запуска непрерывного выполнения
row_num += 1
def fnc_start(event):
    global  mstep_num
    global  flg_execute
    fnc_setsteptau(event)
    flg_execute = 1
    mstep_num = 0       #- номер миллишага в шаге


btn_start = Buttongrid( pnl_prog, row_num, 0, u'старт', 10, fnc_start)

##-- кнопка останова непрерывного выполнения
def fnc_stop(event):
    global  flg_execute
    flg_execute = 0

btn_stop = Buttongrid( pnl_prog, row_num, 1, u'стоп', 10, fnc_stop)

##-- кнопка запуска выполнения в цикле
row_num += 1
def fnc_loop(event):
    global  mstep_num
    global  flg_execute
    fnc_setsteptau(event)
    flg_execute = 2
    mstep_num = 0       #- номер миллишага в шаге


btn_start = Buttongrid( pnl_prog, row_num, 0, u'цикл', 10, fnc_loop)


##-- кнопка записи программы в файл
row_num += 1
def fnc_save(event):
    file_name = filedialog.SaveAs(root, filetypes = [('*.txt files', '.txt')]).show()
    if file_name != '':
        lbx_prog.save(file_name)

btn_save = Buttongrid( pnl_prog, row_num, 0, u'записать', 10, fnc_save)

##-- кнопка чтения программы из файла
def fnc_load(event):
    file_name = filedialog.Open(root, filetypes = [('*.txt files', '.txt')]).show()
    if file_name != '':
        lbx_prog.load(file_name)

btn_load = Buttongrid( pnl_prog, row_num, 1, u'прочитать', 10, fnc_load)


#-- левая панель
pnl_left = ttk.Frame(pnl_main, width = 800)
pnl_left.pack(side = 'left', fill = 'both', expand = 1)

##-- листбокс отправленных строк
lst_log = ['log']

def fnc_lbxlogdbl(ev):
    edt_strout.set( lbx_log.get()[2:] )

lbx_log = Labellistbox( pnl_left, 0,0, u"журнал связи:", 40, row_count, lst_log, fnc_lbxlogdbl, 10, 3 )

##-- кнопка очистки списка отправленныз строк
row_num = 16
def fnc_clearlbxlog(event):
    lbx_log.clear()
btn_clearlbxlog = Buttongrid( pnl_left, row_num, 2, u'очистить', 10, fnc_clearlbxlog)

##-- поле ввода отправляемой строки
row_num += 1
def fnc_sendstrout(event):
    global lst_out
    global busy_out

    str_out = edt_strout.get()
    lbx_log.append( "<=" + str_out)
    #lbx_log.set_index(lbx_log.size()-1 )

    str_out = str_out.split(';')[0].strip()

    if len(str_out)>0:
        while busy_out:
            sleep(0.001)
        busy_out = 3
        lst_out.append(str_out)
        lbx_log.yview(END)
        busy_out = 0

edt_strout = Labelentry( pnl_left, row_num, 0, u'строка:',30,'b015000   ;write_byte   0150  00',fnc_sendstrout, 3 )

##-- кнопка очистки отправляемой строки
row_num += 1

def fnc_clearstrout(event):
    edt_strout.set('')
btn_clearstrout = Buttongrid( pnl_left, row_num, 1, u'очистить', 10, fnc_clearstrout)

##-- кнопка отправки введенной строки

btn_sendstrout = Buttongrid( pnl_left, row_num, 2, u'отправить', 10, fnc_sendstrout)

##-- выпадающий список для выбора отправляемой команды
row_num += 1
dct_cmdout ={"read_memo":"m018010", "write_byte":"b0150f3", "write_word":"w0180112A",
                "write_long":"l015011223344", "write_string":"s0187010203040506",
                "up_bits":"u0150f1", "down_bits":"d015080", "togle_bits":"t015080",
                "reset_chip":"r", "answer_echo":"a54","get_version":"g",
                "out_to_PORTB":"o0150", "in_from_PIND":"i0150",
                "add_byte":"x01500160", "sub_byte":"y01500160", "move_byte":"z01500160",
                "shift_left":"k015001", "shift_right":"q015001", " ":" "}
lst_cmdout = list(dct_cmdout.keys())
lst_cmdout.sort()


def fnc_cbxcmdout(ev):
    cmd_out = cbx_cmdout.get()
    str_out =  dct_cmdout[ cmd_out]
    address = str_out[1:5]
    operand = str_out[5: ]
    str_out = str_out +"   ;"+ cmd_out + "   " + address + "   " + operand
    edt_strout.set(str_out)
    edt_ramaddr.set(address)
    edt_operand.set(operand)

cbx_cmdout = Labelcombobox(pnl_left, row_num, 0, u'команда:', 15, 10, lst_cmdout, fnc_cbxcmdout)

###== функция вставки адреса в строку вывода
def  fn_insaddr(str_out, addr, addropis):
####== структура строки: код, описание команды, описание адреса, описание ореранда
    lst_strout = str_out.split()
    lst_strout.append(" "); lst_strout.append(" "); lst_strout.append(" ");  lst_strout.append(" ");

    str_cod = lst_strout[0]
    lst_strout[0] = str_cod[0] + addr + str_cod[5:]
    lst_strout[2] = addropis
    return("   ".join(lst_strout)  )

##-- поле и кнопка для номера регистра
row_num += 1
def fnc_setregaddr(ev):
    str_out = edt_strout.get()
    reg_num = int( edt_regnum.get())
    reg_addr = hex( reg_num + 65536)[-4:]
    str_out = fn_insaddr(str_out, reg_addr, "R"+str(reg_num))
    edt_strout.set(str_out)

edt_regnum = Labelentry( pnl_left, row_num, 0, u'регистр:',4,'16', fnc_setregaddr )
btn_setregnum = Buttongrid( pnl_left, row_num, 2, u'вставить', 10, fnc_setregaddr)

##-- поле и кнопка для адреса ОЗУ
row_num += 1
def fnc_setramaddr(ev):
    str_out = edt_strout.get()
    ram_addr = edt_ramaddr.get()
    ram_addr = ( "0000"+ram_addr)[-4:]
    str_out = fn_insaddr(str_out, ram_addr, ram_addr)
    edt_strout.set(str_out)

edt_ramaddr = Labelentry( pnl_left, row_num, 0, u'адрес RAM:',8,'0160' )
btn_setramaddr = Buttongrid( pnl_left, row_num, 2, u'вставить', 10, fnc_setramaddr)


##-- поле выбора порта ввода-вывода
row_num += 1
dct_port ={"PIND":"0030", "DDRD":"0031", "PORTD":"0032",
                "PINC":"0033", "DDRC":"0034",
                "PORTC":"0035", "PINB":"0036", "DDRB":"0037",
                "PORTB":"0038",
                "ADCL":"0024", "ADCH":"0025","ADCSRA":"0026", "ADMUX":"0027",
                "ACSR":"0028", "SFIOR":"0050"," ":" "  }
lst_port = list(dct_port.keys())
lst_port.sort()


def fnc_portaddr(ev):
    str_out = edt_strout.get()
    port_name = cbx_port.get()

    str_out = fn_insaddr(str_out, dct_port[ port_name], port_name)
    edt_strout.set(str_out)

cbx_port = Labelcombobox(pnl_left, row_num, 0, u'порт ввода:', 15, 6, lst_port, fnc_portaddr)

##== поле ввода операнда
row_num += 1

def fnc_setoperand(ev):
    str_out = edt_strout.get()
    operand = edt_operand.get()

    if len(operand) % 2 == 1:
        operand = "0"+operand

    lst_strout = str_out.split()
    lst_strout.append(" "); lst_strout.append(" "); lst_strout.append(" ");  lst_strout.append(" ");

    str_cod = lst_strout[0]
    lst_strout[0] = str_cod[0:5] + operand
    lst_strout[3] = operand
    str_out = ("   ".join(lst_strout)  )

    edt_strout.set(str_out)

edt_operand = Labelentry( pnl_left, row_num, 0, u'операнд:',16,'A3', fnc_setoperand)
btn_setoperand = Buttongrid( pnl_left, row_num, 2, u'вставить', 10, fnc_setoperand)


#-- главная функция, запускаемая в цикле
def main():
    global  lst_in
    global  busy_in

    global  flg_execute
    global  mstep_count
    global  mstep_num


    ##-- проверить и вывести данные из устройства
    if len( lst_in ) > 0:
        while busy_in:
            sleep(0.001)
        busy_in = 1
        str_in  = lst_in.pop(0)
        # sio.emit('result', str_in, room = userSid)
        lbx_log.append("=>" + str_in)
        lbx_log.yview(END)
        #lbx_log.set_index(lbx_log.size()-1 )
        busy_in = 0

    ##-- сделать шаг в пошаговом режиме
    if  flg_execute > 0:
        #print mstep_count
        if  mstep_num < mstep_count:    # просто ждать начала шага
            mstep_num += 1
        else:
            mstep_num = 0
            index = lbx_prog.get_index()
            str_out = lbx_prog.get()
            #print index

            if  len(str_out) >2:
                if str_out[0] != ";":
                    edt_strout.set( str_out)
                    fnc_sendstrout(0)
                index += 1
                #print index
                lbx_prog.set_index(index)
            elif flg_execute == 1:   # прекратить при простом пошаговом режиме
                flg_execute = 0
            elif flg_execute == 2:   # вернуться на ближайшую пустую строку в цикле
                if index < 0:
                    lbx_prog.set_index(1)
                    index = lbx_prog.get_index()
                    #print index
                while index > 0:

                    index -= 1
                    lbx_prog.set_index(index)
                    str_out = lbx_prog.get()
                    if len( str_out ) < 1:  break
                if len( str_out ) < 1:
                    lbx_prog.set_index(index + 1)

    ##-- перезапуститься после задержки
    root.after(main_tau, main)


if __name__ == '__main__':
    appSocket.start()
    main()
    #-- запустить окно программы
    root.mainloop()
#-- end
