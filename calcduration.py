import math

#calcduration은 바이트를 받아, 실제 시간으로 프레임 duration을 계산한다. 이후, 그것을 timestep으로 바꾼다.
GI = 0.8 #가드 인터벌, 마이크로세컨드 단위
SYMBOLTIME = 12.8 #심볼 타임, 마이크로세컨드 단위
PRE_LEGACY = 20 #레거시 프리앰블, 마이크로세컨드 단위
PRE_HE_1 = 16 # HE-LTF를 제외한 프리앰블, 마이크로세컨드 단위
PRE_HE_LTF = 4 # HE-LTF, 마이크로세컨드 단위. 공간스트림에 따라 배수됨.


def calcduration(bytes, mcs, cbw, stream): #bytes: 페이로드의 바이트 길이, mcs: mcs 인덱스, stream: 공간 스트림 수, cbw: channel bandwidth
    bps, cod = mcs_interpret(mcs)
    bits = bytes * 8
    spd = cbw_to_tones(cbw) * bps * cod * stream
    symbols = math.ceil(bits / spd)
    mpdu_airtime = math.ceil(symbols / (GI+SYMBOLTIME))
    duration = PRE_LEGACY + PRE_HE_1 + PRE_HE_LTF * stream + mpdu_airtime
    return duration

def cbw_to_tones(cbw):
    if cbw == 160:
        tones = 996*2
    elif cbw == 80:
        tones = 996
    elif cbw == 40:
        tones = 484
    elif cbw == 20:
        tones = 106
    return tones

def mcs_interpret(mcs):
    #bps = bit(s) per symbol
    #cod = coding rate
    if mcs == 0:
        bps = 1
        cod = 0.5
    elif mcs == 1:
        bps = 2
        cod = 0.5
    elif mcs == 2:
        bps = 2
        cod = 0.75
    elif mcs == 3:
        bps = 4
        cod = 0.5
    elif mcs == 4:
        bps = 4
        cod = 0.75
    elif mcs == 5:
        bps = 6
        cod = 0.67
    elif mcs == 6:
        bps = 6
        cod = 0.75
    elif mcs == 7:
        bps = 6
        cod = 0.83
    elif mcs == 8:
        bps = 8
        cod = 0.75
    elif mcs == 9:
        bps = 8
        cod = 0.83
    elif mcs == 10:
        bps = 10
        cod = 0.75
    elif mcs == 11:
        bps = 10
        cod = 0.83
    return bps, cod