import random
import argparse
import math
import csv
import random
from calcduration import calcduration #calcduartion 모듈에서 calcduration 함수를 불러옴
import sys

print(sys.argv)


#r11버전
# 프로그램 매개변수로 시뮬레이터 파라미터 조절 기능 추가
# 구현 예정: 통계 기능: 2. AP가 프레임을 특정 STA로 전송 후 다음 전송하는 STA가 무엇인지 trace
# 구현 예정: PEDCA 피드백 ->언젠가
# (언젠가) 구현 예정: 큐의 프레임에 따른 A-MPDU 자동 생성
# (언젠가) 구현 예정: 물리 파라미터 기반 히든 노드 계산
# (언젠가) 구현 예정. 하지만 중요. : TXOP limit에 비종속되는 프레임 전송 시퀀스 생성

#-----------------------이전 버전 체인지로그
# R5 버전:  중요: PEDCA 구현된 버전임/ receive 함수 버그 잡음(아직 남아있을 가능성 높음) / 그 외 버그 수정함
# R6 버전: 시뮬레이터 파라미터 조절 맨 위로 옮김 / 히든 노드 알고리즘 달라짐(물리 기반으로 수정하는 것이 가장 좋으나, 현 시점에서는 힘든 부분 존재)
# R7 버전: 고정 구간 기반 voice 패킷 입력 /  full-buffer 패킷 입력 (AC_BE) / RTS Time 및 CTS Time 수정
# r8 버전: AP도 이제 프레임을 전송함. / PEDCA Sync 구현 완료 / VO 스케줄러의 치명적 오류 수정
# r9 버전: PEDCA 차등 AIFS 구현 완료
# r10 버전: Receiver RXphydelay 구현 조건에 있는 치명적 문제점 수정 /  구현 완료: 통계 기능: 1. 각 STA들 별 VO 프레임 지연을 CSV로 내보냄

# ----------------------------
# 0. 시뮬레이션 파라미터 설정
# ----------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="PEDCA Simulator Parameters")
    parser.add_argument("--sim_TIME", type=int, default=5000*1000,
                        help="Simulation time in microseconds (default: 5000*1000)")
    parser.add_argument("--num_STA", type=int, default=10,
                        help="Number of STA nodes (default: 10)")
    parser.add_argument("--num_HD", type=int, default=0,
                        help="Number of hidden nodes (default: 0)")
    parser.add_argument("--num_PEDCA", type=int, default=2,
                        help="Number of PEDCA-enabled STA (default: 2)")
    parser.add_argument("--num_VO", type=int, default=4,
                        help="Number of VO-enabled STA (default: 4)")
    parser.add_argument("--PEDCA_SYNC", action="store_true",
                        help="Enable PEDCA_SYNC (default: False)")
    parser.add_argument("--PEDCA_FEEEDBACK", action="store_true",
                        help="Enable PEDCA_FEEEDBACK (default: False)")
    parser.add_argument("--PEDCA_AIFS", action="store_true",
                        help="Enable PEDCA_AIFS (default: False)")
    parser.add_argument("--ICR_MODE", type=int, default=0,
                    help="Internal collision resolution mode, 0 (default) -> PEDCA first, 1 -> Fairness Mode, 2 -> PEDCA time restriction-first mode, 2 -> PEDCA time restriction-fairness mode")
    parser.add_argument("--PEDCA_TIMER", type=int, default=5000,
                    help="PEDCA restriction timer, in microseconds, dafault: 5000us")
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_args()
    
    # 시뮬레이션 파라미터를 args에서 가져와 할당합니다.
    sim_TIME = args.sim_TIME
    num_STA = args.num_STA
    num_HD = args.num_HD
    num_PEDCA = args.num_PEDCA
    num_VO = args.num_VO
    PEDCA_SYNC = args.PEDCA_SYNC
    PEDCA_FEEEDBACK = args.PEDCA_FEEEDBACK
    PEDCA_AIFS = args.PEDCA_AIFS
    ICR_MODE = args.ICR_MODE
    PEDCA_TIMER = args.PEDCA_TIMER


# sim_TIME = 5000*1000 #us 단위 시간 스텝

# #노드 수
# num_STA = 10
# #히든 노드 수
# num_HD = 0
# #PEDCA 사용 STA의 수
# num_PEDCA = 2
# #AC_VO STA 수
# num_VO = 4

# #PEDCA flag (ReLCA Sync, Feedback, diffAC)
# PEDCA_SYNC = False
# PEDCA_FEEEDBACK = False
# PEDCA_AIFS = False

#arrival time of VO frame and bytes of VO frame
vo_arrival_min = 10 * 1000 #dmitry 24/0467 기고 참고
vo_arrival_max = 22 * 1000 #dmitry 24/0467 기고 참고
vo_bytes = 160 + 30 #30: 데이터 프레임 맥 헤더

#airtime 계산을 위한 파라미터들
mcs = 7
cbw = 80
stream = 2
#단일 패킷 airtime
airtime_vo = calcduration(vo_bytes, mcs, cbw, stream)
airtime_vi = None
airtime_be = None
airtime_bk = None

#which ACs are full-buffer?
make_great = ['BE', 'VI']

# 전역 디버그 플래그 (True이면 print가 실행되고, False이면 print가 꺼짐)
DEBUG = True

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)



# ----------------------------
# 1. 기본 파라미터 설정
# ----------------------------


# 기본 시간 파라미터 (us 단위)
aSlotTime = 9       # 9us
aSIFSTime = 13      # 13us
aPIFSTime = 22      # 22us
aRXPHYStartDelay = 24 #24us
aRXTXTurnAroundTime = 4 #4us
acktimeout = aSlotTime + aSIFSTime + aRXPHYStartDelay #사용 안할수도 있다.
AckTxTime = 32
RTS_Time = 32 + 20 #20은 legacy 프리앰블
CTS_Time = 24 + 20 #20은 legacy 프리앰블


#항상 TXOP 끝이 남도록 설정되는 일종의 마진
TXOP_margin = 30
#응답 프레임 길이
response_length = 100

# TXOP limit (ms 단위) → 시뮬레이터 내에서는 us 단위로 변환
TXOP_limit = {
    'VO': RTS_Time + CTS_Time + airtime_vo + response_length + TXOP_margin + 3 * aSIFSTime if airtime_vo is not None else int(2.080 * 1000),
    'VI': RTS_Time + CTS_Time + airtime_vi + response_length + TXOP_margin + 3 * aSIFSTime if airtime_vi is not None else int(4.096 * 1000),
    'BE': RTS_Time + CTS_Time + airtime_be + response_length + TXOP_margin + 3 * aSIFSTime if airtime_be is not None else int(2.528 * 1000),
    'BK': RTS_Time + CTS_Time + airtime_bk + response_length + TXOP_margin + 3 * aSIFSTime if airtime_bk is not None else int(2.528 * 1000),
}

# EDCAF 관련 파라미터
aCWmin = 15
aCWmax = 1023

# AIFSN 값 (AC별)
if PEDCA_AIFS is True: #PEDCA AIFS 차별화가 작동하면,
    AIFSN = {
        'VO': 4,
        'VI': 4,
        'BE': 5,
        'BK': 8,
        'PEDCA': 2
    }
else:
        AIFSN = {
        'VO': 2,
        'VI': 2,
        'BE': 3,
        'BK': 7,
        'PEDCA': 2
    }
    

# AIFS 계산 (us 단위)
AIFS = {ac: aSIFSTime + aSlotTime * AIFSN[ac] for ac in AIFSN}
# EIFS 계산 (us 단위)
EIFS = {ac: aSIFSTime + aSlotTime + AIFS[ac] for ac in AIFSN}

# CWmin 및 CWmax (AC별)
CWmin = {
    'VO': int((aCWmin + 1) / 4 - 1),
    'VI': int((aCWmin + 1) / 2 - 1),
    'BE': aCWmin,
    'BK': aCWmin,
}

CWmax = {
    'VO': int((aCWmin + 1) / 2 - 1),
    'VI': aCWmin,
    'BE': aCWmax,
    'BK': aCWmax,
}

#QSRC 최대값
dot11ShortRetryLimit  = 7 #https://ieeexplore.ieee.org/abstract/document/5997332/?casa_token=3-FOMklDMF8AAAAA:TLzN3Suy9vxvrIryvuNi9k17X99vi-kFY0IofIy9L9RzP8XK2Y9SfotfluNFrl_AfwpG0GheaXXKSxw



#####프레임 템플릿

Template_Data = {
            'enqtime': 0, #큐에 인큐된 시점, 테스트용: 0으로. 실제로는 STA의 클럭대로 인큐해야겠지.
            'start_time': 0, #STA가 전송할 때 설정함., 절대시간
            'end_time': 0, #STA가 전송할 때 설정함., 절대시간
            'tx': None, #전송 STA의 id
            'rx': None, #수신 STA의 id
            'type': 'data',
            'length': 100,   # 전송 길이 예: 100us, 실제 물리적 프레임의 전송 길이를 나타냄
            'duration': 200,  # duration 예: 200us, 프레임이 전송된 후 설정하는 NAV를 나타냄.
            'issoliciting':'blockack', #이 프레임이 어떤 프레임을 응답 프레임으로 요청하나요? 를 지시. :BlockAck, Ack, CTS 등... 없으면 None, Ack 및 CTS의 경우는 고정값임
            'response_len': response_length,#BA가 사용되는 경우 응답 프레임의 길이
            'retry':0, #EDCAF가 사용하는 retry 카운터
            'isoverride': False #수신 판별 시에만 사용: 충돌되는 프레임이 존재하는 경우, 해당 프레임을 개별 STA에서 무시하는 용도의 플래그임 (대체로 이전에 전송된 프레임)
        }


Template_RTS = {
            'enqtime': 0, #큐에 인큐된 시점, 테스트용: 0으로. 실제로는 STA의 클럭대로 인큐해야겠지.
            'start_time': 0, #STA가 전송할 때 설정함., 절대시간
            'end_time': 0, #STA가 전송할 때 설정함., 절대시간
            'tx': None, #전송 STA의 id
            'rx': None, #수신 STA의 id
            'type': 'rts',
            'length': RTS_Time,   # 전송 길이 예: 100us, 실제 물리적 프레임의 전송 길이를 나타냄
            'duration': 0,  # duration
            'issoliciting':'cts', #이 프레임이 어떤 프레임을 응답 프레임으로 요청하는지 지시.

        }

Template_CTS = {
            'enqtime': 0, #큐에 인큐된 시점, 테스트용: 0으로. 실제로는 STA의 클럭대로 인큐해야겠지.
            'start_time': 0, #STA가 전송할 때 설정함., 절대시간
            'end_time': 0, #STA가 전송할 때 설정함., 절대시간
            'tx': None, #전송 STA의 id
            'rx': None, #수신 STA의 id
            'type': 'cts',
            'length': 100,   # 전송 길이 예: 100us, 실제 물리적 프레임의 전송 길이를 나타냄
            'duration': 0,  # duration 예: 200us, 프레임이 전송된 후 설정하는 NAV를 나타냄.
            'issoliciting': None, #이 프레임이 어떤 프레임을 응답 프레임으로 요청하는지 지시.
            'isDS': False, # 이 프레임이 PEDCA DS인지 아닌 지 구분
        }

# ----------------------------
# 2. 클래스 정의
# ----------------------------

class Channel:
    """
    채널 클래스:
    - 프레임 전송 시 송신자, 수신자, 전송 길이, duration 정보를 저장
    - 각 STA에게 현재 전송 중인 프레임 정보를 제공
    """
    def __init__(self):
        self.current_frames = []  # 전송중인 프레임 리스트
        self.framecounter = 0 #프레임의 고유 카운터(id) 기록
        
#    def transmit_frame(self, frame):
#        """
#        프레임 전송 요청을 받으면 리스트에 추가
#        frame: dict, { 'tx': STA id, 'rx': 수신자 id, 'length': 전송 길이(us), 'duration': duration(us), ... }
#        """
#        frame['id'] = self.framecounter #프레임의 순번을 기록함
#        self.framecounter += 1
#        self.current_frames.append(frame)
#        # 이후 충돌 여부, NAV 업데이트 등은 각 STA가 판단
#        debug_print(f"Channel: Frame transmitted from STA {frame['tx']} to STA {frame['rx']} (length: {frame['length']} us, duration: {frame['duration']} us), id: {frame['id']}")
#        debug_print(f"Channel: Current Frames in channel: {self.current_frames}")

    def transmit_frame(self, frame):
        for existing_frame in self.current_frames:
            if (existing_frame.get('start_time', None) == frame.get('start_time', None) and
                existing_frame.get('end_time', None) == frame.get('end_time', None) and
                existing_frame.get('rx', None) == frame.get('rx', None)
                and existing_frame.get('tx', None) == frame.get('tx', None)) :
                print(f"Channel: Identical frame already exists (Frame id: {existing_frame['id']}), {existing_frame} not adding new frame.")
                return
        frame_copy = frame.copy()  # 프레임 딕셔너리의 복사본 생성
        frame_copy['id'] = self.framecounter  # 프레임의 순번을 기록함
        self.framecounter += 1
        self.current_frames.append(frame_copy)
        debug_print(f"Channel: Frame transmitted from STA {frame_copy['tx']} to STA {frame_copy['rx']} (length: {frame_copy['length']} us, duration: {frame_copy['duration']} us), id: {frame_copy['id']}")
        debug_print(f"Channel: Transmitted Frame: {frame_copy}")

    def get_channel_info(self):
        """
        특정 STA가 채널을 조회할 때, 현재 전송중인 프레임 정보를 반환
        """
        # 전체 프레임 정보를 리턴
        return self.current_frames

    def update(self, current_time):
        """
        채널 내의 프레임 전송 진행 상황 업데이트
        예를 들어, 전송이 끝난 프레임은 리스트에서 제거
        """
        # 현재 시간 기반으로 전송 완료한 프레임 제거 (여기서는 간단히 제거)
        finished_frames = []
        for frame in self.current_frames:
            # frame에 시작 시간을 포함시키면, 전송 완료 여부를 판단할 수 있음
            if current_time >= frame.get('start_time', 0) + frame['length']:
                finished_frames.append(frame)
        for frame in finished_frames:
            self.current_frames.remove(frame)

class STA:
    """
    STA 클래스:
    - 4개의 EDCA 대기열 (AC: VO, VI, BE, BK)
    - 채널 접근 (EDCAF) 및 백오프 로직
    - NAV, 응답 프레임 생성, 히든 노드 리스트 관리
    """
    def __init__(self, sta_id, is_ap=False, PEDCA_enabled = False, VO_enabled = False):
        self.PEDCA_enabled = PEDCA_enabled
        self.vo_enabled = VO_enabled
        self.id = sta_id
        self.is_ap = is_ap  # AP 여부

        ###채널 접근용 관리 변수
        # 각 AC별 큐 (여기서는 간단하게 리스트로 구현)
        self.queues = {'VO': [], 'VI': [], 'BE': [], 'BK': []}
        # 각 AC별 백오프 카운터 (None이면 대기 중 아님)
        self.backoff_counters = {'VO': None, 'VI': None, 'BE': None, 'BK': None}
        #백오프 카운터 감소를 위한 백오프 슬롯을 관리하기 위한 변수 (일종의 타이머처럼 동작하고, 0에 도달하면 새로운 슬롯 카운터 값을 설정하고, 백오프 슬롯이 감소함: 예시: AIFS: 31 이후 1씩 감소 / AIFS 이후 9로 초기화 됨..반복)
        self.slot_timers = {'VO': None, 'VI': None, 'BE': None, 'BK': None}
        #PEDCA용 백오프 카운터는 AC_VO slot timer에 의존적으로 감소함.
        self.backoff_counter_PEDCA = None #PEDCA용 백오프 카운터 (AIFS 시간 이후에 전송하는 데에 사용 + short contention에 사용)     
        self.slot_timer_PEDCA = None #PEDCA용 슬롯 카운터 (short contention에서 사용)
        self.DSEndTime = 0 #DS의 전송 종료 시간.이 변수는 PEDCAchannel access 함수에서, 자신의 DS를 필터링 하기 위한 용도로 쓰임.

        #AC별 CW 관리, #AC별 QSRC 관리, #QSRC 최대값
        self.CWcurrent = CWmin #초기값: CWmin
        self.QSRCcurrent = {ac: 0 for ac in AIFSN} #초기값: 0

        ###EDCAF의 타이머 및 채널 접근에 관련된 사항
        self.nav = 0  # NAV 타이머 (us)
        self.txnav = 0 #TXNAV 타이머 (us)-> 이후 수정 필요 (AC별 특정 AC는 전송 가능하고, 나머지 AC는 suspend하는 형식)
        self.isAIFS = False #첫 번째 슬롯 카운터가 AIFS로 업데이트 되어야 하는지 지정하는 플래그, 기본 값은 0이고, 일반적으로 STA가 프레임 정상 수신 후 1로 설정함.
        self.isEIFS = False #이전에 오류가 발생한 프레임이 존재하는 경우 설정되는 일회성 플래그. 슬롯 카운터가 EIFS로 설정되고 바로 0으로 설정되어야 함. STA가 오류가 발생한 프레임을 감지하면 1로 설정함.
        self.forbidPEDCATimer = 0 #PEDCA 제한 동작을 위한 타이머 변수

        ###Tx 및 Receiver 관련 동작에 필요한 변수들
        self.hidden_nodes = []  # 히든 노드 STA id 리스트 (채널에서 수신되는 프레임을 필터링함)
        self.framelog = [] #수신되는 프레임을 기록해둠, receiver 함수에서 사용함
        self.txqueue = [] #EDCAF가 매체 접근을 성공한 경우, 전송을 시도하는 현재 대기중인 프레임을 저장함.
        self.txac = None #EDCAF가 매체 접근을 성공한 경우, 전송을 시도하는 EDCAF를 저장함.
        self.txindex = 0
        self.txframe = None     # 현재 전송 중인 프레임
        self.txend = None
        self.response_received = False  # 응답 프레임 수신 여부
        self.response_wait_start = 0      # 응답 대기 시작 시간
        self.acktimeout = 0 #STA의 EDCAF가 Ack 또는 Blockack이 수신되는 지 아닌지 확인하는 변수 저장용

        ###프레임 인큐 스케줄링을 위한 변수
        self.next_arrival_vo = None

        ###프레임의 전송 성공 기록
        self.successframe = {ac: [] for ac in AIFSN}
        ##프레임의 전송 실패 기록
        self.failframe = {ac: [] for ac in AIFSN}
    
    def make_buffer_great_again(self, current_time): #full buffer 함수
        if self.is_ap == False:
            for ac in make_great: #시뮬레이션 파라미터 셋업에서 바꿀 수 있음.
                if self.queues[ac] == []: #큐가 비어있으면
                    enqframe = Template_Data.copy()
                    enqframe['enqtime'] = current_time
                    enqframe['tx'] = self.id
                    enqframe['rx'] = 0 #수신자는 AP, AP id는 항상 0
                    self.enqueue_frame(ac, enqframe, current_time)
        # else: #AP인 경우
        #     for ac in make_great: #시뮬레이션 파라미터 셋업에서 바꿀 수 있음.
        #         if self.queues[ac] == []: #큐가 비어있으면
        #             enqframe = Template_Data.copy() 
        #             enqframe['enqtime'] = current_time
        #             enqframe['tx'] = self.id
        #             enqframe['rx'] = random.randint(1, num_STA)#num_STA의 id중 하나를 골라 전송
        #             self.enqueue_frame(ac, enqframe, current_time)

    def vo_frame_scheduler(self, current_time):
        if self.vo_enabled == False: #vo enabled STA만 AC_VO 인큐
            return
        if self.next_arrival_vo is None: #아직 변수 초기화가 안된 경우
            self.next_arrival_vo = random.randint(vo_arrival_min, vo_arrival_max) + current_time #dmitry 기고 24/0467 참고
        elif self.next_arrival_vo >= current_time: #아직 arrival time이 안온 경우
            pass
        else:# arrival time이 도달한 경우
            self.next_arrival_vo = random.randint(vo_arrival_min, vo_arrival_max) + current_time
            debug_print(f"[VO scheduleer] VO 입력: 현재 시각: {current_time}, 새 arrival:{self.next_arrival_vo} ")
            if self.is_ap == False: #AP가 아닌 경우에
                voframe = Template_Data.copy()
                voframe['enqtime'] = current_time
                voframe['tx'] = self.id
                voframe['rx'] = 0 #수신자는 AP, AP id는 항상 0
                self.enqueue_frame('VO', voframe, current_time)
            else:
                voframe = Template_Data.copy()
                voframe['enqtime'] = current_time
                voframe['tx'] = self.id
                voframe['rx'] = random.randint(1, num_STA)#num_STA의 id중 하나를 골라 전송
                self.enqueue_frame('VO', voframe, current_time)

    
    def enqueue_frame(self, ac, frame, current_time):
        """
        각 AC별로 프레임을 대기열에 추가
        frame: dict, 프레임 정보 (예: {'tx': self.id, 'rx': target, 'length': 전송 길이, 'duration': duration})
        """
        if frame.get('enqtime', True):#enqtime이 모종의 이유로 없으면
            frame['enqtime'] = current_time

        self.queues[ac].append(frame)
        debug_print(f"STA {self.id}: Enqueued frame in AC {ac}")
    
    def start_backoff(self, ac):
        """
        (Channel access 및 TXOP 함수 종속)
        백오프 카운터 초기화 함수:
         - EDCA에서는 CW 범위 내의 난수를 사용
         - PEDCA의 경우, 짧은 백오프 창 [0, 7] 사용 가능 (여기서는 기본 EDCA와 구분)
        """
        # QSRC를 이용한 현재 ac에 대한 cw 계산함. (CWcurrent는 QSRCcurrent로 계산되기 때문에 불필요할 수 있음.)
        cw = max(CWmin[ac], min(2 ** self.QSRCcurrent[ac] * (CWmin[ac] + 1) - 1 , CWmax[ac]))
        self.backoff_counters[ac] = random.randint(0, cw)
        debug_print(f"STA {self.id}: Start backoff for AC {ac} with counter {self.backoff_counters[ac]}")

    def physical_cs(self, current_time, channel: Channel):
        """
        독립함수
        Physical CS를 추상화하기 위한 함수.
        본 함수는 현재 medium이 busy인지 아닌지를 True/False로 반환함.
        """
        # 채널에 현재 전송중인 프레임들을 받아옴. 
        channel_info = channel.get_channel_info()
        #debug_print(f"[PHYCS] {self.id}의 RAW channel: {channel.get_channel_info()}")
        # 히든 노드 필터링: hidden_nodes에 포함된 STA로부터 전송되는 프레임은 감지하지 않음.(자신이 전송중인 프레임은 감지함.), 이 때, 미래의 프레임도 감지하면 안됨
        #Physical CS는 aRXTXTrunaroundTime 이후의 프레임은 감지하지 못하도록 설정됨.
        channel_info_filtered = [frame for frame in channel_info if (frame['tx'] not in self.hidden_nodes) and (frame.get('start_time', 0) <= current_time - aRXTXTurnAroundTime)]
        #debug_print(f"[PHYCS] {self.id}의 physical cs가 감지중인 프레임: {channel_info_filtered}, 현재시각 {current_time}")
        # 필터링된 프레임이 하나라도 존재하면 medium은 busy 상태로 간주.
        return True if channel_info_filtered else False


    def update_collision_flags(self):
        """
        종속함수 (process framelog 종속)
        framelog에 있는 모든 프레임 쌍에 대해, 서로의 시간 간격이 겹치는지(충돌 여부)를 실시간으로 검사하여,
        겹치는 경우에는 override 및 error 플래그를 설정한다.
        
        두 프레임이 겹치는 조건:
        frame_i['end_time'] > frame_j['start_time'] and frame_j['end_time'] > frame_i['start_time']
        
        두 프레임이 겹칠 경우, 종료 시간이 빠른 쪽(또는 종료 시간이 같다면 id가 작은 쪽)을 override,
        나머지 프레임은 error 플래그를 설정한다.
        """
        n = len(self.framelog)
        for i in range(n):
            for j in range(i + 1, n):
                frame_i = self.framelog[i]
                if frame_i['start_time'] is not None and self.txend is not None:
                    if frame_i['start_time'] <= self.txend and self.txend <= frame_i['end_time']: #자신이 전송중인 프레임의 전송 완료 시점과, 수신되는 프레임의 시작 및 완료 시점이 중첩되면.
                        frame_i['iserror'] = True
                frame_j = self.framelog[j]
                # 충돌 조건: 두 프레임의 구간이 겹치는지 검사
                if (frame_i['end_time'] >= frame_j['start_time'] and frame_j['end_time'] >= frame_i['start_time']):
                    # 겹치면 플래그 업데이트
                    if (frame_i['end_time'] < frame_j['end_time']) or \
    (frame_i['end_time'] == frame_j['end_time'] and frame_i['id'] < frame_j['id']):
                        frame_i['isoverride'] = True
                        frame_j['iserror'] = True
                    else:
                        frame_i['iserror'] = True
                        frame_j['isoverride'] = True

    def process_framelog(self, current_time):
        """
        종속함수(receive 함수 종속)
        framelog 내의 프레임들에 대해 실시간으로 충돌 플래그를 업데이트한 후,
        현재 시간이 각 프레임의 end_time에 도달한 프레임(ready_frames)을 대상으로 이벤트를 발생시킨다.
        
        - ready_frames에 대해:
        * frame에 iserror 플래그가 설정되어 있으면 collision 이벤트를 발생
        * 그렇지 않으면 success 이벤트를 발생
        - 이벤트 발생 후 해당 프레임은 framelog에서 제거된다.
        
        반환값은 처리된 프레임들에 대한 이벤트 리스트이며, 예) [("collision", frame1), ("success", frame2)].
        처리할 프레임이 없으면 None을 반환한다.
        """
        # 먼저 framelog 내 모든 프레임에 대해 충돌 플래그를 실시간 업데이트
        self.update_collision_flags()
        
        # 현재 시간이 도래한 프레임들만 ready_frames로 선정
        ready_frames = [frame for frame in self.framelog if current_time >= frame['end_time']]
        events = []
        
        for frame in ready_frames:
            if frame.get('iserror', False):
                events.append(("collision", frame))
            elif frame.get('isoverride', False):
                pass
            else:
                events.append(("success", frame))
            # 처리한 프레임은 framelog에서 제거
            self.framelog.remove(frame)
        
        return events if events else None

    def receive(self, current_time, channel: Channel):
        """
        독립함수
        프레임을 수신하고, 프레임의 충돌 여부를 판단하는 함수. (프레임의 virtual carrier sensing 로직 및 프레임의 수신에 따른 후속 동작 처리 함수)
        - 자신이 전송중이 아닌 경우 동작
        - 채널에서 수신된 프레임들을 framelog에 기록(중복 id는 기록하지 않음)
        - 프레임의 end_time에 도달한 경우에만, framelog를 기반으로 충돌 여부를 판단하여,
        충돌이 발생하면 collision 이벤트를 채널 접근 함수에 넘기고, 그렇지 않으면 정상 수신 이벤트를 반환.
        """

        # 채널의 현재 전송중인 프레임들을 받아옴.
        channel_info = channel.get_channel_info()
        #debug_print(f"STA{self.id}, 현재 채널 상황: {channel_info}")
        # 히든 노드, self, 미래의 프레임 필터링: hidden_nodes에 포함된 STA로부터 전송된 프레임은 무시하고, 자기 자신의 프레임도 무시. -> 자기 자신의 프레임으로 NAV를 설정하는 일은 없음.
        filtered_frames = [frame.copy() for frame in channel_info if (frame['tx'] not in self.hidden_nodes) and (frame['tx'] != self.id) and (frame['start_time'] <= current_time - aRXPHYStartDelay)]
        
        # 새로운 프레임을 framelog에 추가 (이미 기록된 프레임 id는 건너뜀)
        for frame in filtered_frames:
            if all(frame['id'] != existing_frame['id'] for existing_frame in self.framelog):
                self.framelog.append(frame.copy())

        if self.txframe is not None and current_time < self.txframe['end_time'] + aRXTXTurnAroundTime:
            debug_print(f"[RECV]: STA {self.id}: 현재 전송 중이어서 수신 동작을 건너뜁니다. 현재 시각 {current_time}") #자신의 프레임 말고, 다른 전송중인 프레임에 대해서는 error로 기록해야 함,.
            return
 
        # 현재 시간이 각 프레임의 end_time에 도달했을 때만, framelog 내 프레임들을 대상으로 충돌 검사 수행
        receive_result = self.process_framelog(current_time)
        if receive_result is not None:
            if len(receive_result) > 1:  # 프레임 완료 이벤트가 2개라면 오류임
                debug_print(f"[RECV] STA{self.id}는 프레임을 수신했습니다. 충돌입니다. 프레임 완료 이벤트가 2개 이상 동시에 발생했습니다. 현재 시각{current_time}")
                self.isEIFS = True
            elif any(event[0] == "collision" for event in receive_result):  # 충돌이 포함되어 있으면
                debug_print(f"[RECV] STA{self.id}는 프레임을 수신했습니다. 충돌입니다. 충돌 이벤트가 framelog 처리 과정에서 발생했습니다. 현재 시각{current_time}")
                debug_print(f"[RECV]: 수신 결과 {receive_result}, RAW channel: {channel.get_channel_info()}")
                self.isEIFS = True
            elif current_time == receive_result[0][1]['end_time']:
                # 정상 수신인 경우, 프레임의 수신자에 따른 응답 프레임 전송 및 NAV 업데이트
                #프레임을 정상 수신했기 때문에, EIFS 사용은 안함
                #프레임을 정상 수신했기 때문에, AIFS 사용을 True로 만듦.
                debug_print(f"[RECV] STA{self.id}는 프레임을 정상 수신했습니다. 현재 시각{current_time}. frame id{receive_result[0][1]['id']} 수신 결과 {receive_result} ")
                self.isEIFS = False
                self.isAIFS = True

                if PEDCA_SYNC == True and self.PEDCA_enabled == True and receive_result[0][1].get('isDS', False) == True: #PEDCA Sync 구현 - 다른 STA의 DS를 수신하면, 즉시 PEDCA로 fallback
                    if len(self.queues['VO']) !=0:
                        self.txac = 'PEDCA'
                        self.slot_timer_PEDCA = aSlotTime
                        self.backoff_counter_PEDCA = random.randint(0, 7) #short backoff counter 선정
                        self.DSEndTime = receive_result[0][1].get('end_time')
                        debug_print(f"[RECV]: STA {self.id} DS Sync가 동작합니다.")
                        return

                if receive_result[0][1]['rx'] == self.id: #수신되는 프레임이 자신의 프레임이고, 프레임의 종류에 따른 동작 수행
                    debug_print(f"[RECV] STA{self.id} 수신된 프레임은 수신 대상입니다.")
                    #자신이 수신자인 프레임은 NAV 업데이트는 안함
                    #데이터 프레임인 경우, 응답 프레임 생성 함수에 수신된 프레임을 넘김
                    #Ack 프레임이나 BlockAck 프레임과 같은 응답 프레임인 경우, 자신의 전송 대상 프레임의 전송 성공을 보고
                    if receive_result[0][1]['issoliciting'] is not None:#수신된 프레임이 응답 프레임을 요구하지 않는 프레임이 아니라면(not None) 항상 수신된 프레임을 response generator로 넘김
                        debug_print(f"[RECV] STA{self.id} 수신된 프레임은 데이터 프레임입니다.")
                        self.response_generator(current_time, channel, receive_result[0][1])
                    elif receive_result[0][1]['type'] == 'ack' or receive_result[0][1]['type'] == 'blockack' or receive_result[0][1]['type'] == 'cts':
                        #if self.txframe['rx'] == receive_result[0][1]['tx']: CTS 프레임에서는 사용할 수 없음
                        debug_print(f"[RECV] STA{self.id} 수신된 프레임은 응답 프레임입니다.")
                        self.response_received = True

                elif receive_result[0][1]['rx'] != self.id: #수신되는 프레임이 자신의 프레임이 아니면
                    frame_duration = receive_result[0][1]['duration']
                    self.nav = max(frame_duration, self.nav)

    def response_generator(self, current_time, channel: Channel, received_frame):
        """
        종속함수: receive 함수 종속
        즉시 응답 프레임을 aSIFSTime 이후에 생성합니다.
        즉시 응답 프레임은 수신된 프레임의 정보에 따라 생성되고, 채널 접근 함수와 별도로 독립적으로 채널에 응답 프레임을 전송합니다.
        """
        
        response_frame = {
            'enqtime': 0, #큐에 인큐된 시점, 테스트용: 0으로. 실제로는 STA의 클럭대로 인큐해야겠지.
            'start_time': 0, #STA가 전송할 때 설정함., 절대시간
            'end_time': 0, #STA가 전송할 때 설정함., 절대시간
            'tx': None, #전송 STA의 id
            'rx': None, #수신 STA의 id
            'type': 'data',
            'length': 100,   # 전송 길이 예: 100us, 실제 물리적 프레임의 전송 길이를 나타냄
            'duration': 200,  # duration 예: 200us, 프레임이 전송된 후 설정하는 NAV를 나타냄.
            'issoliciting':None, #이 프레임이 어떤 프레임을 응답 프레임으로 요청하나요? 를 지시. :BlockAck, Ack, CTS 등... 없으면 None
            'response_len': 0, #요구되는 응답 프레임의 길이
        }
        response_frame['start_time'] = current_time + aSIFSTime #SIFS 후에 전송되는 미래의 프레임
        response_frame['tx'] = received_frame['rx']
        response_frame['rx'] = received_frame['tx'] #송수신자 변경

        if received_frame['issoliciting'] == 'ack':#normal ack인 응답 프레임인 경우
            response_frame['type'] = 'ack'
            response_frame['length'] = AckTxTime #normal ack 길이
            response_frame['duration'] = max(received_frame['duration'] - response_frame['length'] - aSIFSTime, 0)#수신된 프레임의 duration에서 응답 프레임의 길이 및 SIFS를 빼서 응답 프레임의 duration으로 생성
            #응답 프레임의 듀레이션이 남은 duration 필드를 초과할 수 있고, 이 경우는 duration은 0임
        elif received_frame['issoliciting'] == 'cts':#cts 프레임인 응답 프레임이면
            response_frame['type'] = 'cts'
            response_frame['length'] = CTS_Time #CTS 길이
            response_frame['duration'] = max(received_frame['duration'] - response_frame['length'] - aSIFSTime, 0)#수신된 프레임의 duration에서 응답 프레임의 길이 및 SIFS를 빼서 응답 프레임의 duration으로 생성
            #응답 프레임의 듀레이션이 남은 duration 필드를 초과할 수 있고, 이 경우는 duration은 0임
            response_frame['tx'] = None #CTS 프레임은 TA 필드가 없음.
        else: #요구하는 응답 프레임의 종류에 따른 응답 프레임의 타입 결정, 예를 들어 blockack
            response_frame['type'] = received_frame['issoliciting']
            response_frame['length'] = received_frame['response_len']
            response_frame['duration'] = max(received_frame['duration'] - response_frame['length'] - aSIFSTime, 0)#수신된 프레임의 duration에서 응답 프레임의 길이 및 SIFS를 빼서 응답 프레임의 duration으로 생성
            #응답 프레임의 듀레이션이 남은 duration 필드를 초과할 수 있고, 이 경우는 duration은 0임

        response_frame['end_time'] = response_frame['start_time'] + response_frame['length']#응답 프레임 타입에 따른 응답 프레임의 절대 end_time 계산 가능

        channel.transmit_frame(response_frame) #채널에 생성된 응답 프레임을 전송

    def channel_access(self, current_time, channel: Channel):
        """
        독립함수
        채널 접근 함수:
        EDCAF별로, 프레임 전송을 위한 백오프 동작을 수행한다.
        
        구현 내용:
        - 각 EDCAF(AC)에 대해, 1us마다 슬롯 타이머를 1씩 감소시킨다.
        - isAIFS가 True인 경우, 해당 EDCAF의 최초 슬롯 타이머를 AIFS[AC]로 설정하고, self.isAIFS를 False로 설정한다.
        - isEIFS가 True이면, 해당 EDCAF의 최초 슬롯 타이머를 EIFS[AC]로 설정하고, self.isEIFS와 self.isAIFS를 False로 설정한다.
            (isEIFS의 우선순위가 더 높음)
        - isAIFS가 False이면, 이후 슬롯 타이머는 aSlotTime(9us)로 초기화된다.
        - 슬롯 타이머가 0 이하가 되면, 백오프 카운터를 1씩 감소시킨다.
        - 백오프 카운터가 -1이 될 때, 슬롯 경계에서 TXOP을 획득한다. 이 때, internal collision resolution을 수행한다.
        - 채널 접근 동작 수행 중에, 물리적 채널이 busy 상태가 감지되면, 각 EDCAF의 슬롯 타이머를 위와 같이 초기 상태로 재설정한다.
        """
        if self.txac is not None: #TXOP이 전송중이면 채널접근 안함 
            return
        complete_EDCAF = [] #백오프 카운터가 -1이 된 EDCAF들을 기록
        counter_internal_transmit = 0 #내부 충돌을 감지하기 위한 변수, 1이면 1개의 EDCAF만 전송 시도, 2개 이상이면 내부충돌로 백오프 재시도

        if (ICR_MODE == 2 or ICR_MODE == 3) and self.forbidPEDCATimer > 0: #PEDCA 제약 모드에서, PEDCA 제약 타이머가 0 이상의 값인 경우, PEDCA 타이머를 0이 될 때 까지 감소
            self.forbidPEDCATimer =- 1


        for ac in ['VO', 'VI', 'BE', 'BK']:
            # 해당 AC에 전송할 프레임이 대기열에 있는 경우에만 처리
            if self.queues[ac]:
                # 물리적 채널 및 NAV 상태 확인 (busy이면)
                #debug_print(f"[ChannelAccess] STA {self.id} AC {ac}: physical_cs={self.physical_cs(current_time, channel)}, nav={self.nav}, slot_timer={self.slot_timers.get(ac)}, backoff = {self.backoff_counters[ac]}")
                if self.physical_cs(current_time, channel) or self.nav > 0:
                    #debug_print(f"STA {self.id} : physicalCS {self.physical_cs(current_time, channel)} / nav: {self.nav}")
                    # 채널이 busy 상태이면 슬롯 타이머를 초기 상태로 재설정
                    if self.isEIFS:
                        #debug_print(f"[ChannelAccess] STA {self.id}: set to EIFS")
                        self.slot_timers[ac] = EIFS[ac]
                        if self.PEDCA_enabled and ac == 'VO':
                            self.slot_timer_PEDCA = EIFS['PEDCA']
                        #self.isEIFS = False
                        #self.isAIFS = False
                    elif self.isAIFS:
                        #debug_print(f"[ChannelAccess] STA {self.id}: set to AIFS")
                        self.slot_timers[ac] = AIFS[ac]
                        if self.PEDCA_enabled and ac == 'VO':
                            self.slot_timer_PEDCA = AIFS['PEDCA']
                        #self.isAIFS = False
                    else:
                        #debug_print(f"[ChannelAccess] STA {self.id}: set to aSlotTime")
                        self.slot_timers[ac] = aSlotTime  # 기본 슬롯 타이머 값 (9us)
                        if self.PEDCA_enabled and ac == 'VO':
                            self.slot_timer_PEDCA = aSlotTime
                    # busy 상태에서는 백오프 진행 없이 다음 us로 넘어감
                    continue

                # 물리 채널 및 NAV가 idle 상태인 경우
                # 슬롯 타이머가 아직 초기화되지 않았다면 초기값 설정
                if self.slot_timers[ac] is None:
                    if self.isEIFS:
                        self.slot_timers[ac] = EIFS[ac]
                        #self.isEIFS = False
                        #self.isAIFS = False
                    elif self.isAIFS:
                        self.slot_timers[ac] = AIFS[ac]
                        #self.isAIFS = False
                    else:
                        self.slot_timers[ac] = aSlotTime

                if self.PEDCA_enabled and self.slot_timer_PEDCA is None:
                    if self.isEIFS:
                            self.slot_timer_PEDCA = EIFS['PEDCA']
                    elif self.isAIFS:
                            self.slot_timer_PEDCA = AIFS['PEDCA']
                    else:
                            self.slot_timer_PEDCA = aSlotTime

                # 1us마다 슬롯 타이머 감소
                self.slot_timers[ac] -= 1
                if self.PEDCA_enabled and ac == 'VO':
                    self.slot_timer_PEDCA -= 1

                if self.PEDCA_enabled and self.slot_timer_PEDCA <= 0 and ac == 'VO':
                    if self.backoff_counter_PEDCA == None:
                        self.backoff_counter_PEDCA = 0 #백오프 카운터는 초기값 0으로 설정
                    else:
                        self.backoff_counter_PEDCA -=1 #백오프 카운터 1 감소
                        

                # 슬롯 타이머가 0 이하라면, 슬롯 경계에 도달한 것으로 간주
                if self.slot_timers[ac] <= 0:
                    self.isEIFS = False #1번의 슬롯 경계를 넘은 경우 다음은 aSlot
                    self.isAIFS = False #1번의 슬롯 경계를 넘은 경우 다음은 aSlot
                    self.slot_timers[ac] = aSlotTime#slottimer 초기화
                    # 백오프 카운터가 아직 초기화되지 않았다면 초기화
                    if self.backoff_counters[ac] is None:
                        self.start_backoff(ac)
                    else: #아니면 백오프 카운터를 1 감소함
                        self.backoff_counters[ac] -= 1

                    # 백오프 카운터가 -1이면, TXOP을 획득 시도함 -> -1인 이유는 AIFS에서 줄어드는 백오프 카운터를 고려한 것.
                    #버그! 백오프 카운터를 reinvoke 안되게 만드는 문제점이 어딘가 존재함!
                    if self.backoff_counters[ac] <= -1:
                        counter_internal_transmit += 1
                        complete_EDCAF.append(ac)
                        debug_print(f"STA {self.id} {ac}에 대한 채널 접근 성공: 현재 {ac} 백오프: {self.backoff_counters[ac]} 그리고 슬롯타이머: {self.slot_timers[ac]}")

                    if ac == 'VO' and self.PEDCA_enabled and self.backoff_counter_PEDCA is not None: #PEDCA를 사용하고, PEDCA 백오프 카운터가 존재하고, 
                        if ((ICR_MODE == 2 or ICR_MODE == 3) and self.forbidPEDCATimer <=0) or (ICR_MODE != 2): #내부 충돌 해소 모드가 PEDCA 제약 모드이면, PEDCA 제약 타이머가 0일 때. 또는, PEDCA 제약 모드가 아님. 이 경우, 사전 내부충돌 절차 해소 시작
                            if self.backoff_counter_PEDCA <= -1:
                                counter_internal_transmit += 1
                                complete_EDCAF.append('PEDCA')
                                debug_print(f"STA {self.id} PEDCA 채널 접근 성공: 현재 PEDCA 백오프: {self.backoff_counter_PEDCA} 그리고 슬롯타이머 VO: {self.slot_timers[ac]}")
                                if 'VO' in complete_EDCAF: #VO와 PEDCA 충돌 발생 시, 사전 내부충돌 해소
                                    complete_EDCAF.pop(complete_EDCAF.index('VO'))#VO 제거
                                    self.start_backoff('VO')#QSRC 변경 없이 백오프 수행
                                    self.slot_timers['VO'] = AIFS['VO']
                        else:
                            self.backoff_counter_PEDCA = 0 #내부 충돌 해소 모드가 PEDCA 제약 모드이고, PEDCA타이머가 0보다 큰 경우에는 PEDCA 백오프 카운터를 다시 초기화함.

        #debug_print(f"STA {self.id}: 백오프: {self.backoff_counters}")
        #internal collision resolution #internal trasnmit 수가 1 초과이면 internal collision. internal collision이 발생하면, contention windows를 2배 늘림, QSRC 증가.
        if (ICR_MODE == 0 or ICR_MODE == 2) and counter_internal_transmit > 1: #PEDCA 우선 모드, PEDCA 시간 제약 모드
            for ac in ['BK', 'BE', 'VI', 'VO', 'PEDCA']: #가장 우선순위가 높은 EDCAF만을 남기기 위해, 우선순위가 낮은 AC 순서대로 for문을 돌림, 내부 충돌 해소 절차 수행
                if len(complete_EDCAF)==1: #아래의 QSRC 증가 코드에 의해 QSRC 증가되고, 가상 최상위 EDCAF는 반복문을 돌지 않고 전송됨
                    break
                if ac in complete_EDCAF:
                    complete_EDCAF.pop(complete_EDCAF.index(ac))
                    counter_internal_transmit -= 1 #내부 전송 카운터 감소
                    self.QSRCcurrent[ac] +=1
                    if self.QSRCcurrent[ac] > dot11ShortRetryLimit:
                        self.QSRCcurrent[ac] = 0
                        current_frame = self.queues[ac].pop(0) #전송 실패로 프레임 드롭
                        current_frame['end_time'] = current_time #프레임의 종료 시점에 이 드롭된 프레임이 겪은 딜레이를 기록함.
                        self.failframe[ac].append(current_frame)
                    self.start_backoff(ac) #내부 충돌 발생한 AC는 증가된 QSRC 바탕으로 백오프 진행함
                    self.slot_timers[ac] = AIFS[ac]

        elif (ICR_MODE == 1 or ICR_MODE == 3) and counter_internal_transmit > 1: #Fairness 모드 (PEDCA는 우선순위 제외), PEDCA 시간 제약 fairness 모드
            for ac in ['PEDCA', 'BK', 'BE', 'VI', 'VO']: #가장 우선순위가 높은 EDCAF만을 남기기 위해, 우선순위가 낮은 AC 순서대로 for문을 돌림. PEDCA를 가장 우선적으로 제거함.
                if len(complete_EDCAF)==1: #아래의 QSRC 증가 코드에 의해 QSRC 증가되고, 가상 최상위 EDCAF는 반복문을 돌지 않고 전송됨
                    break
                if ac in complete_EDCAF:
                    complete_EDCAF.pop(complete_EDCAF.index(ac))
                    counter_internal_transmit -= 1 #내부 전송 카운터 감소
                    if ac == 'PEDCA': #PEDCA의 경우, 특별한 백오프 초기화 조건(QSRC 증가 X) 필요함.
                        self.backoff_counter_PEDCA = 0 #PEDCA 백오프 카운터 0 설정, 그리고 반복문 탈출
                        self.slot_timers[ac] = AIFS['PEDCA']
                        break
                    self.QSRCcurrent[ac] +=1
                    if self.QSRCcurrent[ac] > dot11ShortRetryLimit:
                        self.QSRCcurrent[ac] = 0
                        current_frame = self.queues[ac].pop(0) #전송 실패로 프레임 드롭
                        current_frame['end_time'] = current_time #프레임의 종료 시점에 이 드롭된 프레임이 겪은 딜레이를 기록함.
                        self.failframe[ac].append(current_frame)
                    self.start_backoff(ac) #내부 충돌 발생한 AC는 증가된 QSRC 바탕으로 백오프 진행함
                    self.slot_timers[ac] = AIFS[ac]        

        
        if counter_internal_transmit == 1: #전송 가능 EDCAF가 1개인 경우에 전송 동작 시작
            print(counter_internal_transmit, "success EDCAF: ", complete_EDCAF)
            if 'PEDCA' not in complete_EDCAF: #PEDCA가 아닌 경우
                txframe = self.queues[complete_EDCAF[0]][0] #실제로 전송 대기열에서 제거하지는 않음. 이는 txop 함수가 해야 함.
                self.txac = complete_EDCAF[0]
                #현재는 모든 AC별 RTS-CTS를 구현하고자 함, 현재 AP는 프레임 전송을 안하는 것으로 구현함 = AP는 프레임 인큐를 안함.
                #RTS 프레임을 설정함
                rtsframe = Template_RTS.copy()
                rtsframe['tx'] = self.id
                if self.is_ap == 0:
                    rtsframe['rx'] = 0 #수신자는 AP임
                    rtsframe['duration'] = TXOP_limit[complete_EDCAF[0]] - RTS_Time - aSIFSTime - TXOP_margin  #RTS 듀레이션 설정, STA는 margin 사용 안함
                else: #AP의 RTS 프레임 전송
                    rtsframe['rx'] = txframe['rx']
                    rtsframe['duration'] = TXOP_limit[complete_EDCAF[0]] - RTS_Time - aSIFSTime  #RTS 듀레이션 설정
                #데이터 프레임을 설정함
                txframe['length'] = TXOP_limit[complete_EDCAF[0]] - RTS_Time - CTS_Time - response_length - TXOP_margin - 3 * aSIFSTime #데이터 프레임의 실제 전송 길이 계산 
                txframe['duration'] = rtsframe['duration'] - CTS_Time - aSIFSTime - txframe['length']
                self.txqueue = []#초기화
                self.txqueue.append(rtsframe)
                self.txqueue.append(txframe)
                #frame = self.queues[ac].pop(0)
                #frame['start_time'] = current_time
                #frame['end_time'] = current_time + frame['length']
                #channel.transmit_frame(frame)
                # 전송 후 백오프 카운터 초기화
                #self.backoff_counters[ac] = None
                # 다음 슬롯 타이머는 기본 슬롯 값(aSlotTime)으로 재설정
            else: #PEDCA가 채널 접근에 성공한 경우: DS 전송 후 PEDCA channel access 함수를 불러옴
                defersignal = Template_CTS.copy()
                defersignal['isDS'] = True
                defersignal['rx'] = 0
                defersignal['start_time'] = current_time
                defersignal['end_time'] = current_time + defersignal['length']
                defersignal['duration'] = 7*aSlotTime #Defersignal이 설정하는 NAV
                self.DSEndTime = defersignal['end_time']
                channel.transmit_frame(defersignal)
                self.slot_timer_PEDCA = aSlotTime
                self.backoff_counter_PEDCA = random.randint(0, 7) #short backoff counter 선정
                self.txac = 'PEDCA' #채널 접근 방지용.
        
    def PEDCA_channel_access(self, current_time, channel: Channel): #txac가 PEDCA로 되어 있으면, short contention 수행.
        if self.txac is None or self.txac != 'PEDCA' or self.PEDCA_enabled == False: #txac가 PEDCA가 아닌 경우, return
            return
        elif current_time > self.DSEndTime:
            if self.physical_cs(current_time, channel) is False: #phycs로 medium이 idle이면
                self.slot_timer_PEDCA -= 1 #1 감소
                debug_print(f"[PEDCA channel] STA {self.id}: PEDCA slot timer {self.slot_timer_PEDCA}")
                if self.slot_timer_PEDCA <= 0:
                    self.slot_timer_PEDCA = aSlotTime
                    self.backoff_counter_PEDCA -= 1 #short backoff counter 1 감소
                
                if self.backoff_counter_PEDCA <= -1: #short backoff counter가 -1에 도달하면, TXOP 호출
                    ############아래 코드들은 channel_Access 함수에서 가져온 것으로, 해당 함수가 변경되면 아래도 변경 필요함.
                    txframe = self.queues['VO'][0] #실제로 전송 대기열에서 제거하지는 않음. 이는 txop 함수가 해야 함.
                    #현재 AP는 프레임 전송을 안하는 것으로 구현함 = AP는 프레임 인큐를 안함.
                    #RTS 프레임을 설정함
                    rtsframe = Template_RTS.copy()
                    rtsframe['tx'] = self.id
                    if self.is_ap == 0:
                        rtsframe['rx'] = 0 #수신자는 AP임
                    else:
                        pass #현재 AP 구현은 없음
                    rtsframe['duration'] = TXOP_limit['VO'] - RTS_Time - aSIFSTime  #RTS 듀레이션 설정

                    #데이터 프레임을 설정함
                    txframe['length'] = TXOP_limit['VO'] - RTS_Time - CTS_Time - response_length - TXOP_margin - 3 * aSIFSTime #데이터 프레임의 실제 전송 길이 계산 
                    txframe['duration'] = rtsframe['duration'] - CTS_Time - aSIFSTime - txframe['length']
                    self.txqueue = []#초기화
                    self.txqueue.append(rtsframe)
                    self.txqueue.append(txframe)
                    self.txac = 'VO' #TXOP은 TXAC를 VO로 인식하게 함.
                    self.slot_timer_PEDCA = AIFS['VO']
                    self.backoff_counter_PEDCA = 0

#            elif current_time <= self.DSEndTime: #phycs가 busy여도 아직 DS 종료시점에 도달하지 않았으면, 아무 일도 일어나지 않음.
#                pass

            else: #백오프 중간에 phycs busy이면, PEDCA short contention 실패
                debug_print(f"[PEDCA channel] STA {self.id}: phycs로 PEDCA 절차가 중단됨. 현재 시각 {current_time}, DS 종료 시간: {self.DSEndTime}")
                self.slot_timer_PEDCA = aSlotTime
                self.backoff_counter_PEDCA = 0
                self.txac = None

    def txop(self, current_time, channel: Channel): #txac PEDCA에 대한 추가 정의가 필요함.
        """
        프레임을 실질적으로 전송하는 TXOP 함수
        txqueue에 프레임을 input하고, 전송 완료하면 ac의 백오프를 개시함
        txop 함수: 각 EDCAF(AC)에 대해, txindex가 0이면 무조건 프레임을 전송하고,
        이후에는 응답 프레임 수신 여부에 따라 동작.
        """
        # txindex가 0이면 즉시 프레임 전송  (최초 전송 - 본 시뮬레이터에서는 무조건 RTS 프레임이기 때문에 항상 전송 성공으로 하기)
        #if self.txac is not None:
        #    debug_print(f"[txop] STA {self.id} at time {current_time}: txindex={self.txindex}, txac={self.txac}, backoff={self.backoff_counters[self.txac]}, slot_timer={self.slot_timers[self.txac]}")
        if self.txac == None or self.txac == 'PEDCA':
            return

        if self.txindex == 0:
            if self.txqueue: #큐에 프레임이 있으면
                debug_print(f"[TXOP] STA {self.id}의 최초 프레임 전송 / txindex={self.txindex}, txac={self.txac},backoff={self.backoff_counters[self.txac]}, slot_timer={self.slot_timers[self.txac]}")
                frame = self.txqueue[self.txindex]
                frame['start_time'] = current_time
                frame['end_time'] = current_time + frame['length']
                channel.transmit_frame(frame)
                self.txframe = frame
                self.txend = frame['end_time']
                # 만약 응답 프레임이 요구되지 않는다면 즉시 성공 처리
                if frame.get('issoliciting') is None:
                    #frame['success_time'] = current_time + frame['length']
                    #self.successframe.append(frame) RTS 프레임을 전송 성공 로그에 넣으면 안됨.
                    self.response_received = True #응답 프레임이 없어도 되는 프레임은 응답 프레임을 수신한 것으로 간주함. -> 아래 응답 프레임 수신된 경우로 넘어감
                else:
                    # 응답 프레임 요구: 응답 대기 시작
                    #self.response_wait_start = current_time
                    self.response_received = False
                self.txindex = 1 #최초 전송 후 1로 설정
                    
            else:
                # 전송할 프레임이 없으면 아무것도 안 함
                #debug_print(f"[TXOP] STA {self.id}의 최초 프레임 전송 / txindex={self.txindex} / 최초로 전송할 프레임이 없습니다.")
                pass
        else: #최초 프레임이 아닌 프레임을 전송 (이전 전송 프레임 존재)
            # txindex > 0: 
            if self.response_received:
                debug_print(f"[TXOP] STA {self.id} 응답 프레임을 수신했습니다.")
                # 응답 프레임 수신 후 SIFS 시간 이후에 다음 프레임 전송
                if current_time >= self.txframe['end_time'] + aSIFSTime: #의미 없음. 나중에 지워야 함.
                    debug_print(f"[TXOP] STA {self.id} 응답 프레임 수신 후 전송할 다음 프레임을 전송합니다.")
                    if len(self.txqueue) - 1 >= self.txindex: #최초 프레임 전송 후에도 남은 프레임이 있는 것을 확인 (본 시뮬에서는 데이터 프레임임)
                        frame = self.txqueue[self.txindex]
                        frame['start_time'] = current_time + aSIFSTime #응답 프레임 수신 후 SIFS후에 전송
                        frame['end_time'] = current_time + frame['length']
                        channel.transmit_frame(frame)
                        self.txframe = frame
                        self.txend = frame['end_time']
                        self.txindex += 1
                        if frame.get('issoliciting') is None:
                            frame['success_time'] = current_time + frame['length']
                            self.successframe[self.txac].append(frame)
                            self.response_received = True #응답 프레임이 없어도 되는 프레임은 응답 프레임을 수신한 것으로 간주함.
                            self.queues[self.txac].pop(0)#ac별 대기열에서 프레임 제거
                        else:
                            self.response_received = False

                    else:
                        #전송 큐가 비었고(전송 큐 길이보다 txindex가 커짐), 응답 프레임을 수신하면 이전에 전송한 데이터 프레임은 성공한 것임.
                        # 또한, 전송 큐에 남은 프레임이 없으면 모든 프레임 전송 완료: 백오프 시작 및 QSRC 초기화
                        debug_print(f"[TXOP] STA {self.id} TXOP의 모든 프레임 전송 성공")
                        self.txframe['success_time'] = current_time
                        self.successframe[self.txac].append(self.txframe) #성공한 데이터 프레임을 큐에 넣음
                        self.response_received = False #응답 프레임 수신 상태를 원상태로 초기화
                        self.queues[self.txac].pop(0) #ac별 대기열에서 프레임 제거
                        self.response_received = False
                        self.QSRCcurrent[self.txac] = 0
                        self.start_backoff(self.txac)
                        self.isAIFS = True #post backoff 시 AIFS 사용
                        self.slot_timers = AIFS.copy()
                        self.response_received = False #응답 프레임 수신 상태를 원상태로 초기화
                        self.txac = None
                        self.txindex = 0
                        self.txqueue = [] #전송큐 초기화
                        self.txframe = None
                        self.txend = None
            else:
                # 응답 프레임이 수신되지 않은 경우
                expected_response_time = self.txframe['end_time'] + aSIFSTime + aRXPHYStartDelay + response_length #응답 프레임 수신 대기를 위한 시간 - 프레임 길이 기반 - 본 시뮬레이터에서, 프레임이 수신되는 시점으로 이를 계산함. 실제 표준과 약간 다름.
                #debug_print(f"[TXOP] STA {self.id} 응답 프레임 수신을 대기합니다. {expected_response_time} 시간 내에 응답 프레임이 수신되어야 합니다.")
                if current_time >= expected_response_time:
                    # 응답 타임아웃 -> 전송 실패 처리
                    debug_print(f"[TXOP] STA {self.id} 응답 프레임 수신이 안됐습니다. {expected_response_time} 시간 내에 응답 프레임이 수신되지 않음.")
                    self.QSRCcurrent[self.txac] += 1
                    if self.QSRCcurrent[self.txac] > dot11ShortRetryLimit: #QSRC를 넘어서 AC별 큐의 프레임이 완전 실패한 것임.
                        self.QSRCcurrent[self.txac] = 0
                        self.queues[self.txac].pop(0) #ac별 대기열에서 프레임 제거
                        current_frame = self.txframe
                        current_frame['end_time'] = current_time
                        self.failframe[self.txac].append(current_frame)
                    self.start_backoff(self.txac) #post-backoff
                    self.isAIFS = True #post backoff 시 AIFS 사용
                    self.slot_timers = AIFS.copy()
                    # txqueue 초기화
                    self.txqueue = []
                    self.txframe = None
                    self.txac = None
                    self.txindex = 0
                    self.response_received = False

    def update(self, current_time, channel: Channel):
        """
        최상위함수: 독립함수들을 구동함
        매 시간(1us 단위)마다 호출되는 STA의 업데이트 함수.
        - NAV 타이머 감소
        - 채널 접근 및 백오프 로직 처리
        - 프레임 전송 시도 처리(timeout 처리)
        """
        # NAV 타이머 감소
        if self.nav > 0:
            self.nav -= 1
        self.make_buffer_great_again(current_time) #full buffer 함수
        self.vo_frame_scheduler(current_time) #vo 트래픽 스케줄링용 함수
        self.receive(current_time, channel)
        self.channel_access(current_time, channel)
        self.PEDCA_channel_access(current_time, channel)
        self.txop(current_time, channel)



class Simulator:
    """
    메인 시뮬레이터 클래스:
    - 1us 단위 시뮬레이션 클럭 관리
    - STA 및 AP 생성, 채널 모듈과의 인터페이스 관리
    """
    def __init__(self, sim_time_us, num_stations, num_hidden):
        self.clock = 0
        self.sim_time = sim_time_us
        self.channel = Channel()
        self.stations = []
        # AP는 별도 객체 혹은 STA의 일종으로 처리 (여기서는 STA에서 is_ap=True)
        self.ap = STA(sta_id=0, is_ap=True)
        self.stations.append(self.ap)
        # 나머지 STA 생성
        for i in range(1, num_stations + 1):
            sta = STA(sta_id=i)
            self.stations.append(sta)
        # 히든 노드 설정
        self.configure_hidden_nodes(num_hidden)
        
    # def configure_hidden_nodes(self, num_hidden):
    #     num_sta = len(self.stations)
    #     # 간단하게 첫 num_hidden STA를 서로 히든 노드 관계로 지정
    #     hidden_ids = [sta.id for sta in self.stations[1:num_hidden+1]]
    #     print(hidden_ids)
    #     for sta in self.stations[1:num_hidden+1]:
    #         # 예를 들어, STA의 히든 노드 리스트에 다른 STA의 id 추가 (자기 자신 제외)
    #         sta.hidden_nodes = [hid for hid in hidden_ids if hid != sta.id]
    #         print(f"STA {sta.id} hidden nodes: {sta.hidden_nodes}")

    def configure_hidden_nodes(self, num_hidden):
        """
        AP를 제외한 모든 STA에 대해, 각 STA가 정확히 num_hidden개의 히든 노드를 갖도록 대칭적 관계를 설정합니다.
        만약 num_hidden이 STA 수-1보다 크면, 가능한 최대값으로 설정합니다.
        """
        # AP를 제외한 STA 리스트 생성
        sta_list = [sta for sta in self.stations if not sta.is_ap]
        N = len(sta_list)
        # 각 STA는 최대 (N-1)개의 히든 노드를 가질 수 있음
        d = min(num_hidden, N - 1)

        # 모든 STA의 hidden_nodes를 빈 집합으로 초기화 (대칭관계를 쉽게 처리하기 위해 집합으로 처리)
        for sta in sta_list:
            sta.hidden_nodes = set()

        # 모든 STA가 d개의 히든 노드를 가질 때까지 반복
        # 간단한 히든 노드 추가 알고리즘: 아직 degree가 부족한 STA들 중 임의의 두 개를 선택하여 서로를 추가
        # (만약 추가할 수 없는 경우도 있겠지만, d가 상대적으로 작으면 충분히 설정 가능할 것입니다.)
        while any(len(sta.hidden_nodes) < d for sta in sta_list):
            # 아직 degree가 부족한 STA들 목록
            available = [sta for sta in sta_list if len(sta.hidden_nodes) < d]
            if len(available) < 2:
                break  # 더 이상 연결할 STA가 없다면 종료
            a, b = random.sample(available, 2)
            # 만약 a와 b가 아직 연결되어 있지 않다면, 서로를 추가
            if b.id not in a.hidden_nodes:
                a.hidden_nodes.add(b.id)
                b.hidden_nodes.add(a.id)
                print(f"STA {a.id}와 STA {b.id}는 서로의 히든 노드로 설정되었습니다.")

        # 집합을 리스트로 변환 (필요한 경우)
        for sta in sta_list:
            sta.hidden_nodes = list(sta.hidden_nodes)
            print(f"STA {sta.id} hidden nodes: {sta.hidden_nodes}")

    
    def run(self):
        """
        시뮬레이션 루프: 1us 단위 시간 진행
        """
        while self.clock < self.sim_time:
            #debug_print("-------------------------------------------------")
            if(self.clock % 1000 == 0):
                print(f"[SIM] 현재 시뮬레이터 시각은 {self.clock} 입니다.")
            #debug_print("-------------------------------------------------")
            # 각 STA 업데이트
            stas = self.stations[:]  # 복사본 생성
            random.shuffle(stas)
            for sta in stas:
                sta.update(self.clock, self.channel)
            self.channel.update(self.clock)
            self.clock += 1


####################로그출력################################
def export_sta_stats(stations, filename="sta_framelog_numsta{0}_numvo_{1}_numpedca{2}_icrmode{3}.csv".format(num_STA, num_VO, num_PEDCA, ICR_MODE)):
    # CSV 필드 이름 설정
    fieldnames = ["sta_id", "PEDCA_enabled", "ac", "enqtime", "transmit_time", "delay", "frame_type", "result", "id"]
    with open(filename, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        # 각 STA마다 로그 export
        for sta in stations:
            for ac in sta.successframe:
                for frame in sta.successframe[ac]:
                    # 성공 시 delay = success_time - enqtime
                    delay = frame["success_time"] - frame["enqtime"]
                    writer.writerow({
                        "sta_id": sta.id,
                        "PEDCA_enabled": sta.PEDCA_enabled,
                        "ac": ac,
                        "enqtime": frame.get("enqtime"),
                        "transmit_time": frame["success_time"],
                        "delay": delay,
                        "frame_type": frame["type"],
                        "result": "success"
                    })
            for ac in sta.failframe:
                for frame in sta.failframe[ac]:
                    # 실패 시 delay = end_time - enqtime
                    delay = frame["end_time"] - frame["enqtime"]
                    writer.writerow({
                        "sta_id": sta.id,
                        "PEDCA_enabled": sta.PEDCA_enabled,
                        "ac": ac,
                        "enqtime": frame.get("enqtime"),
                        "transmit_time": frame["end_time"],
                        "delay": delay,
                        "frame_type": frame["type"],
                        "result": "failure"
                    })

########################################################


# ----------------------------
# 3. 시뮬레이터 실행 예시
# ----------------------------

if __name__ == '__main__':
    # 예: 1,000,000us (1ms가 아니라 1s에 가까운 시간) 동안 10개의 STA (AP 포함 1 AP + 9 STA) 시뮬레이션, 히든 노드 수 지정
    sim = Simulator(sim_time_us=sim_TIME, num_stations=num_STA, num_hidden = num_HD)
    for sta in sim.stations[1:num_PEDCA + 1]:
        sta.PEDCA_enabled = True #지정된 STA들의 PEDCA를 설정함
    for sta in sim.stations[1:num_VO + 1]:
        sta.vo_enabled = True #지정된 STA들의 PEDCA를 설정함
    # 시뮬레이션 실행
    sim.run()
    print("Simulation finished.")

    for sta in sim.stations[0:]:
        print(f"=============STA {sta.id} 결과================")
        print("ACVO 성공:", len(sta.successframe['VO']), "ACVO 실패:", len(sta.failframe['VO']))
        print("ACVI 성공:", len(sta.successframe['VI']), "ACVI 실패:", len(sta.failframe['VI']))
        print("ACBE 성공:", len(sta.successframe['BE']), "ACBE 실패:", len(sta.failframe['BE']))
        print("ACBK 성공:", len(sta.successframe['BK']), "ACBK 실패:", len(sta.failframe['BK']))

    export_sta_stats(sim.stations)
