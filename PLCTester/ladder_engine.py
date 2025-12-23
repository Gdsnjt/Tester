"""
ラダー回路エンジン
Pythonコードでラダー回路を記述・実行
"""
from typing import Dict, List, Callable, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import threading

from plc_devices import PLCDeviceManager
from mc_protocol import DeviceType


class InstructionType(Enum):
    """命令タイプ"""
    # 接点命令
    LD = "LD"       # a接点（ロード）
    LDI = "LDI"     # b接点（ロードインバース）
    AND = "AND"     # a接点直列
    ANI = "ANI"     # b接点直列
    OR = "OR"       # a接点並列
    ORI = "ORI"     # b接点並列
    
    # 接続命令
    ANB = "ANB"     # ブロック直列
    ORB = "ORB"     # ブロック並列
    MPS = "MPS"     # プッシュ
    MRD = "MRD"     # リード
    MPP = "MPP"     # ポップ
    
    # 出力命令
    OUT = "OUT"     # 出力
    SET = "SET"     # セット
    RST = "RST"     # リセット
    PLS = "PLS"     # パルス（立上り）
    PLF = "PLF"     # パルス（立下り）
    
    # タイマ・カウンタ
    OUT_T = "OUT_T"   # タイマ出力
    OUT_C = "OUT_C"   # カウンタ出力
    RST_T = "RST_T"   # タイマリセット
    RST_C = "RST_C"   # カウンタリセット
    
    # 演算命令
    MOV = "MOV"     # 転送
    ADD = "ADD"     # 加算
    SUB = "SUB"     # 減算
    MUL = "MUL"     # 乗算
    DIV = "DIV"     # 除算
    CMP = "CMP"     # 比較
    
    # 制御命令
    END = "END"     # 終了
    NOP = "NOP"     # 無処理


@dataclass
class Device:
    """デバイス参照"""
    device_type: DeviceType
    address: int
    
    def __str__(self):
        return f"{self.device_type.code}{self.address}"
    
    @classmethod
    def parse(cls, text: str) -> 'Device':
        """文字列からデバイスを解析 (例: "M0", "D100")"""
        text = text.upper().strip()
        
        # 2文字デバイスコードを先にチェック
        for dt in DeviceType:
            if text.startswith(dt.code) and len(dt.code) == 2:
                addr_str = text[2:]
                if addr_str.isdigit() or (dt.code in ['X', 'Y', 'B', 'W'] and all(c in '0123456789ABCDEF' for c in addr_str)):
                    base = 16 if dt.code in ['X', 'Y', 'B', 'W'] else 10
                    return cls(dt, int(addr_str, base))
        
        # 1文字デバイスコード
        for dt in DeviceType:
            if text.startswith(dt.code) and len(dt.code) == 1:
                addr_str = text[1:]
                if addr_str.isdigit() or (dt.code in ['X', 'Y', 'B', 'W'] and all(c in '0123456789ABCDEF' for c in addr_str)):
                    base = 16 if dt.code in ['X', 'Y', 'B', 'W'] else 10
                    return cls(dt, int(addr_str, base))
        
        raise ValueError(f"Invalid device: {text}")


@dataclass
class Instruction:
    """ラダー命令"""
    type: InstructionType
    operands: List[Any] = field(default_factory=list)
    
    def __str__(self):
        ops = ', '.join(str(o) for o in self.operands)
        return f"{self.type.value} {ops}" if ops else self.type.value


@dataclass
class TimerState:
    """タイマ状態"""
    is_running: bool = False
    start_time: float = 0.0
    set_value: int = 0  # x100ms
    current_value: int = 0  # x100ms
    contact: bool = False


@dataclass
class CounterState:
    """カウンタ状態"""
    count: int = 0
    set_value: int = 0
    contact: bool = False
    prev_input: bool = False


class LadderProgram:
    """ラダープログラム"""
    
    def __init__(self, name: str = ""):
        self.name = name
        self.instructions: List[Instruction] = []
        self._prev_bits: Dict[str, bool] = {}  # パルス用
    
    def clear(self):
        """プログラムをクリア"""
        self.instructions.clear()
        self._prev_bits.clear()
    
    # === 接点命令 ===
    
    def LD(self, device: str) -> 'LadderProgram':
        """a接点ロード"""
        self.instructions.append(Instruction(InstructionType.LD, [Device.parse(device)]))
        return self
    
    def LDI(self, device: str) -> 'LadderProgram':
        """b接点ロード"""
        self.instructions.append(Instruction(InstructionType.LDI, [Device.parse(device)]))
        return self
    
    def AND(self, device: str) -> 'LadderProgram':
        """a接点直列"""
        self.instructions.append(Instruction(InstructionType.AND, [Device.parse(device)]))
        return self
    
    def ANI(self, device: str) -> 'LadderProgram':
        """b接点直列"""
        self.instructions.append(Instruction(InstructionType.ANI, [Device.parse(device)]))
        return self
    
    def OR(self, device: str) -> 'LadderProgram':
        """a接点並列"""
        self.instructions.append(Instruction(InstructionType.OR, [Device.parse(device)]))
        return self
    
    def ORI(self, device: str) -> 'LadderProgram':
        """b接点並列"""
        self.instructions.append(Instruction(InstructionType.ORI, [Device.parse(device)]))
        return self
    
    # === 接続命令 ===
    
    def ANB(self) -> 'LadderProgram':
        """ブロック直列"""
        self.instructions.append(Instruction(InstructionType.ANB))
        return self
    
    def ORB(self) -> 'LadderProgram':
        """ブロック並列"""
        self.instructions.append(Instruction(InstructionType.ORB))
        return self
    
    def MPS(self) -> 'LadderProgram':
        """プッシュ"""
        self.instructions.append(Instruction(InstructionType.MPS))
        return self
    
    def MRD(self) -> 'LadderProgram':
        """リード"""
        self.instructions.append(Instruction(InstructionType.MRD))
        return self
    
    def MPP(self) -> 'LadderProgram':
        """ポップ"""
        self.instructions.append(Instruction(InstructionType.MPP))
        return self
    
    # === 出力命令 ===
    
    def OUT(self, device: str) -> 'LadderProgram':
        """出力"""
        self.instructions.append(Instruction(InstructionType.OUT, [Device.parse(device)]))
        return self
    
    def SET(self, device: str) -> 'LadderProgram':
        """セット"""
        self.instructions.append(Instruction(InstructionType.SET, [Device.parse(device)]))
        return self
    
    def RST(self, device: str) -> 'LadderProgram':
        """リセット"""
        self.instructions.append(Instruction(InstructionType.RST, [Device.parse(device)]))
        return self
    
    def PLS(self, device: str) -> 'LadderProgram':
        """パルス（立上り）"""
        self.instructions.append(Instruction(InstructionType.PLS, [Device.parse(device)]))
        return self
    
    def PLF(self, device: str) -> 'LadderProgram':
        """パルス（立下り）"""
        self.instructions.append(Instruction(InstructionType.PLF, [Device.parse(device)]))
        return self
    
    # === タイマ・カウンタ ===
    
    def OUT_T(self, timer_no: int, set_value: int) -> 'LadderProgram':
        """タイマ出力 (set_value: x100ms)"""
        self.instructions.append(Instruction(InstructionType.OUT_T, [timer_no, set_value]))
        return self
    
    def OUT_C(self, counter_no: int, set_value: int) -> 'LadderProgram':
        """カウンタ出力"""
        self.instructions.append(Instruction(InstructionType.OUT_C, [counter_no, set_value]))
        return self
    
    def RST_T(self, timer_no: int) -> 'LadderProgram':
        """タイマリセット"""
        self.instructions.append(Instruction(InstructionType.RST_T, [timer_no]))
        return self
    
    def RST_C(self, counter_no: int) -> 'LadderProgram':
        """カウンタリセット"""
        self.instructions.append(Instruction(InstructionType.RST_C, [counter_no]))
        return self
    
    # === 演算命令 ===
    
    def MOV(self, src: Any, dest: str) -> 'LadderProgram':
        """転送"""
        src_val = src if isinstance(src, int) else Device.parse(src)
        self.instructions.append(Instruction(InstructionType.MOV, [src_val, Device.parse(dest)]))
        return self
    
    def ADD(self, src1: Any, src2: Any, dest: str) -> 'LadderProgram':
        """加算"""
        s1 = src1 if isinstance(src1, int) else Device.parse(src1)
        s2 = src2 if isinstance(src2, int) else Device.parse(src2)
        self.instructions.append(Instruction(InstructionType.ADD, [s1, s2, Device.parse(dest)]))
        return self
    
    def SUB(self, src1: Any, src2: Any, dest: str) -> 'LadderProgram':
        """減算"""
        s1 = src1 if isinstance(src1, int) else Device.parse(src1)
        s2 = src2 if isinstance(src2, int) else Device.parse(src2)
        self.instructions.append(Instruction(InstructionType.SUB, [s1, s2, Device.parse(dest)]))
        return self
    
    def MUL(self, src1: Any, src2: Any, dest: str) -> 'LadderProgram':
        """乗算"""
        s1 = src1 if isinstance(src1, int) else Device.parse(src1)
        s2 = src2 if isinstance(src2, int) else Device.parse(src2)
        self.instructions.append(Instruction(InstructionType.MUL, [s1, s2, Device.parse(dest)]))
        return self
    
    def DIV(self, src1: Any, src2: Any, dest: str) -> 'LadderProgram':
        """除算"""
        s1 = src1 if isinstance(src1, int) else Device.parse(src1)
        s2 = src2 if isinstance(src2, int) else Device.parse(src2)
        self.instructions.append(Instruction(InstructionType.DIV, [s1, s2, Device.parse(dest)]))
        return self
    
    # === 制御命令 ===
    
    def END(self) -> 'LadderProgram':
        """終了"""
        self.instructions.append(Instruction(InstructionType.END))
        return self
    
    def NOP(self) -> 'LadderProgram':
        """無処理"""
        self.instructions.append(Instruction(InstructionType.NOP))
        return self
    
    def __str__(self):
        lines = [f"=== Ladder Program: {self.name} ==="]
        for i, inst in enumerate(self.instructions):
            lines.append(f"{i:4d}: {inst}")
        return '\n'.join(lines)


class LadderEngine:
    """ラダー実行エンジン"""
    
    def __init__(self, device_manager: PLCDeviceManager):
        self.devices = device_manager
        
        # プログラム
        self.programs: List[LadderProgram] = []
        
        # タイマ・カウンタ状態
        self.timers: Dict[int, TimerState] = {}
        self.counters: Dict[int, CounterState] = {}
        
        # パルス用前回値
        self._prev_bits: Dict[str, bool] = {}
        
        # 実行状態
        self.is_running = False
        self.scan_count = 0
        self.scan_time = 0.0
        
        # スレッド
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # スキャンタイム（ミリ秒）
        self.scan_interval_ms = 10
    
    def add_program(self, program: LadderProgram):
        """プログラムを追加"""
        self.programs.append(program)
    
    def clear_programs(self):
        """全プログラムをクリア"""
        self.programs.clear()
        self._prev_bits.clear()
    
    def start(self):
        """実行開始"""
        if self.is_running:
            return
        
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """実行停止"""
        if not self.is_running:
            return
        
        self.is_running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
    
    def _run_loop(self):
        """実行ループ"""
        while not self._stop_event.is_set():
            start = time.perf_counter()
            
            self.execute_scan()
            
            self.scan_time = (time.perf_counter() - start) * 1000
            
            # 待機
            wait_time = (self.scan_interval_ms - self.scan_time) / 1000
            if wait_time > 0:
                self._stop_event.wait(wait_time)
    
    def execute_scan(self):
        """1スキャン実行"""
        self.scan_count += 1
        
        # タイマ更新
        self._update_timers()
        
        # 全プログラム実行
        for program in self.programs:
            self._execute_program(program)
    
    def _execute_program(self, program: LadderProgram):
        """プログラムを実行"""
        stack: List[bool] = []  # 演算スタック
        memory_stack: List[bool] = []  # MPS/MRD/MPP用
        current = False
        
        for inst in program.instructions:
            try:
                if inst.type == InstructionType.LD:
                    if current and stack:
                        pass  # 既存のcurrentはそのまま
                    current = self._get_bit(inst.operands[0])
                    stack.append(current)
                
                elif inst.type == InstructionType.LDI:
                    current = not self._get_bit(inst.operands[0])
                    stack.append(current)
                
                elif inst.type == InstructionType.AND:
                    current = current and self._get_bit(inst.operands[0])
                
                elif inst.type == InstructionType.ANI:
                    current = current and not self._get_bit(inst.operands[0])
                
                elif inst.type == InstructionType.OR:
                    current = current or self._get_bit(inst.operands[0])
                
                elif inst.type == InstructionType.ORI:
                    current = current or not self._get_bit(inst.operands[0])
                
                elif inst.type == InstructionType.ANB:
                    if len(stack) >= 2:
                        b = stack.pop()
                        a = stack.pop()
                        current = a and b
                        stack.append(current)
                
                elif inst.type == InstructionType.ORB:
                    if len(stack) >= 2:
                        b = stack.pop()
                        a = stack.pop()
                        current = a or b
                        stack.append(current)
                
                elif inst.type == InstructionType.MPS:
                    memory_stack.append(current)
                
                elif inst.type == InstructionType.MRD:
                    if memory_stack:
                        current = memory_stack[-1]
                
                elif inst.type == InstructionType.MPP:
                    if memory_stack:
                        current = memory_stack.pop()
                
                elif inst.type == InstructionType.OUT:
                    self._set_bit(inst.operands[0], current)
                
                elif inst.type == InstructionType.SET:
                    if current:
                        self._set_bit(inst.operands[0], True)
                
                elif inst.type == InstructionType.RST:
                    if current:
                        self._set_bit(inst.operands[0], False)
                
                elif inst.type == InstructionType.PLS:
                    key = str(inst.operands[0])
                    prev = self._prev_bits.get(key, False)
                    self._set_bit(inst.operands[0], current and not prev)
                    self._prev_bits[key] = current
                
                elif inst.type == InstructionType.PLF:
                    key = str(inst.operands[0])
                    prev = self._prev_bits.get(key, False)
                    self._set_bit(inst.operands[0], not current and prev)
                    self._prev_bits[key] = current
                
                elif inst.type == InstructionType.OUT_T:
                    timer_no = inst.operands[0]
                    set_value = inst.operands[1]
                    self._process_timer(timer_no, set_value, current)
                
                elif inst.type == InstructionType.OUT_C:
                    counter_no = inst.operands[0]
                    set_value = inst.operands[1]
                    self._process_counter(counter_no, set_value, current)
                
                elif inst.type == InstructionType.RST_T:
                    if current:
                        timer_no = inst.operands[0]
                        if timer_no in self.timers:
                            self.timers[timer_no] = TimerState()
                            self.devices.set_bit(DeviceType.TC, timer_no, False)
                            self.devices.set_bit(DeviceType.TS, timer_no, False)
                            self.devices.set_word(DeviceType.TN, timer_no, 0)
                
                elif inst.type == InstructionType.RST_C:
                    if current:
                        counter_no = inst.operands[0]
                        if counter_no in self.counters:
                            self.counters[counter_no] = CounterState()
                            self.devices.set_bit(DeviceType.CC, counter_no, False)
                            self.devices.set_bit(DeviceType.CS, counter_no, False)
                            self.devices.set_word(DeviceType.CN, counter_no, 0)
                
                elif inst.type == InstructionType.MOV:
                    if current:
                        val = self._get_value(inst.operands[0])
                        self._set_word(inst.operands[1], val)
                
                elif inst.type == InstructionType.ADD:
                    if current:
                        v1 = self._get_value(inst.operands[0])
                        v2 = self._get_value(inst.operands[1])
                        self._set_word(inst.operands[2], (v1 + v2) & 0xFFFF)
                
                elif inst.type == InstructionType.SUB:
                    if current:
                        v1 = self._get_value(inst.operands[0])
                        v2 = self._get_value(inst.operands[1])
                        self._set_word(inst.operands[2], (v1 - v2) & 0xFFFF)
                
                elif inst.type == InstructionType.MUL:
                    if current:
                        v1 = self._get_value(inst.operands[0])
                        v2 = self._get_value(inst.operands[1])
                        result = v1 * v2
                        self._set_word(inst.operands[2], result & 0xFFFF)
                
                elif inst.type == InstructionType.DIV:
                    if current:
                        v1 = self._get_value(inst.operands[0])
                        v2 = self._get_value(inst.operands[1])
                        if v2 != 0:
                            self._set_word(inst.operands[2], v1 // v2)
                
                elif inst.type == InstructionType.END:
                    break
                
                elif inst.type == InstructionType.NOP:
                    pass
                    
            except Exception as e:
                print(f"Instruction error: {inst} - {e}")
    
    def _get_bit(self, device: Device) -> bool:
        """ビットを取得"""
        # タイマ・カウンタ接点の場合
        if device.device_type == DeviceType.TC:
            return self.timers.get(device.address, TimerState()).contact
        if device.device_type == DeviceType.CC:
            return self.counters.get(device.address, CounterState()).contact
        
        return self.devices.get_bit(device.device_type, device.address)
    
    def _set_bit(self, device: Device, value: bool):
        """ビットを設定"""
        self.devices.set_bit(device.device_type, device.address, value)
    
    def _get_word(self, device: Device) -> int:
        """ワードを取得"""
        if device.device_type == DeviceType.TN:
            return self.timers.get(device.address, TimerState()).current_value
        if device.device_type == DeviceType.CN:
            return self.counters.get(device.address, CounterState()).count
        
        return self.devices.get_word(device.device_type, device.address)
    
    def _set_word(self, device: Device, value: int):
        """ワードを設定"""
        self.devices.set_word(device.device_type, device.address, value)
    
    def _get_value(self, operand) -> int:
        """オペランドの値を取得"""
        if isinstance(operand, int):
            return operand
        elif isinstance(operand, Device):
            return self._get_word(operand)
        return 0
    
    def _update_timers(self):
        """タイマを更新"""
        current_time = time.time()
        
        for timer_no, state in self.timers.items():
            if state.is_running:
                elapsed = current_time - state.start_time
                state.current_value = int(elapsed * 10)  # x100ms
                
                if state.current_value >= state.set_value:
                    state.contact = True
                    state.current_value = state.set_value
                
                # デバイス更新
                self.devices.set_word(DeviceType.TN, timer_no, state.current_value)
                self.devices.set_bit(DeviceType.TC, timer_no, state.contact)
    
    def _process_timer(self, timer_no: int, set_value: int, input_on: bool):
        """タイマ処理"""
        if timer_no not in self.timers:
            self.timers[timer_no] = TimerState()
        
        state = self.timers[timer_no]
        state.set_value = set_value
        
        if input_on:
            if not state.is_running:
                state.is_running = True
                state.start_time = time.time()
            self.devices.set_bit(DeviceType.TS, timer_no, True)
        else:
            state.is_running = False
            state.current_value = 0
            state.contact = False
            self.devices.set_bit(DeviceType.TS, timer_no, False)
            self.devices.set_bit(DeviceType.TC, timer_no, False)
            self.devices.set_word(DeviceType.TN, timer_no, 0)
    
    def _process_counter(self, counter_no: int, set_value: int, input_on: bool):
        """カウンタ処理"""
        if counter_no not in self.counters:
            self.counters[counter_no] = CounterState()
        
        state = self.counters[counter_no]
        state.set_value = set_value
        
        # 立上りエッジでカウント
        if input_on and not state.prev_input:
            if not state.contact:  # 未到達時のみカウント
                state.count += 1
                self.devices.set_word(DeviceType.CN, counter_no, state.count)
                
                if state.count >= state.set_value:
                    state.contact = True
                    self.devices.set_bit(DeviceType.CC, counter_no, True)
        
        state.prev_input = input_on
        self.devices.set_bit(DeviceType.CS, counter_no, input_on)
    
    def reset_timers(self):
        """全タイマをリセット"""
        self.timers.clear()
    
    def reset_counters(self):
        """全カウンタをリセット"""
        self.counters.clear()
    
    def reset_all(self):
        """全状態をリセット"""
        self.reset_timers()
        self.reset_counters()
        self._prev_bits.clear()
        self.scan_count = 0


# === サンプルラダープログラム ===

def create_sample_program_1() -> LadderProgram:
    """
    サンプル1: 基本的な自己保持回路
    
    X0を押すとY0がON、X1を押すとOFF
    """
    program = LadderProgram("自己保持回路")
    
    # X0 OR Y0 かつ NOT X1 → Y0
    program.LD("X0").OR("Y0").ANI("X1").OUT("Y0").END()
    
    return program


def create_sample_program_2() -> LadderProgram:
    """
    サンプル2: タイマ回路
    
    X0がONで2秒後にY0がON
    """
    program = LadderProgram("タイマ回路")
    
    program.LD("X0").OUT_T(0, 20)  # T0, 2秒
    program.LD("TC0").OUT("Y0")
    program.END()
    
    return program


def create_sample_program_3() -> LadderProgram:
    """
    サンプル3: カウンタ回路
    
    X0の立上り5回でY0がON
    """
    program = LadderProgram("カウンタ回路")
    
    program.LD("X0").OUT_C(0, 5)  # C0, 5カウント
    program.LD("CC0").OUT("Y0")
    program.LD("X1").RST_C(0)  # X1でリセット
    program.END()
    
    return program


def create_sample_program_4() -> LadderProgram:
    """
    サンプル4: データ演算
    
    D0とD1を加算してD2に格納
    """
    program = LadderProgram("データ演算")
    
    program.LD("M0").ADD("D0", "D1", "D2")
    program.LD("M1").SUB("D0", "D1", "D3")
    program.LD("M2").MOV(100, "D10")
    program.END()
    
    return program


def create_sample_program_5() -> LadderProgram:
    """
    サンプル5: 複雑な条件回路
    
    (X0 AND X1) OR (X2 AND X3) → Y0
    """
    program = LadderProgram("複雑条件")
    
    program.LD("X0").AND("X1")
    program.LD("X2").AND("X3")
    program.ORB()
    program.OUT("Y0")
    program.END()
    
    return program
