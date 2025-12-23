"""
GX Works2互換ラダー記述
GX Works2のラダー回路に似た方法でPythonコードを記述可能

使用例:
    ladder = GXLadder("メインプログラム")
    
    # 自己保持回路
    ladder.network(1, "自己保持回路")
    ladder.LD("X0")
    ladder.OR("Y0")
    ladder.ANI("X1")
    ladder.OUT("Y0")
    
    # タイマ回路
    ladder.network(2, "タイマ回路")
    ladder.LD("X2")
    ladder.OUT_T("T0", "K20")  # T0, 2秒
    ladder.LD("T0")
    ladder.OUT("Y1")
"""
import re
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from ladder_engine import LadderProgram, InstructionType, Device, Instruction
from mc_protocol import DeviceType


@dataclass
class NetworkComment:
    """ネットワークコメント"""
    network_no: int
    comment: str


@dataclass
class DeviceComment:
    """デバイスコメント"""
    device: str
    comment: str


class GXLadder:
    """
    GX Works2互換ラダー記述クラス
    
    GX Works2のラダー回路に似た形式でPythonコードを記述できます。
    """
    
    def __init__(self, name: str = ""):
        self.name = name
        self.program = LadderProgram(name)
        
        # ネットワーク管理
        self.current_network = 0
        self.network_comments: Dict[int, str] = {}
        
        # デバイスコメント
        self.device_comments: Dict[str, str] = {}
        
        # K定数、H定数のサポート
        self._constants: Dict[str, int] = {}
    
    def network(self, no: int, comment: str = "") -> 'GXLadder':
        """
        ネットワークを開始
        
        GX Works2のネットワーク番号とコメントに対応
        """
        self.current_network = no
        if comment:
            self.network_comments[no] = comment
        return self
    
    def comment(self, device: str, text: str) -> 'GXLadder':
        """
        デバイスコメントを設定
        
        GX Works2のデバイスコメントに対応
        """
        self.device_comments[device.upper()] = text
        return self
    
    def _parse_constant(self, value: str) -> int:
        """K定数、H定数を解析"""
        value = str(value).upper().strip()
        
        if value.startswith('K'):
            return int(value[1:])
        elif value.startswith('H'):
            return int(value[1:], 16)
        elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
            return int(value)
        else:
            # デバイス参照の場合はそのまま返す（後で解決）
            return value
    
    # === 接点命令（GX Works2形式） ===
    
    def LD(self, device: str) -> 'GXLadder':
        """ロード（a接点）"""
        self.program.LD(device)
        return self
    
    def LDI(self, device: str) -> 'GXLadder':
        """ロードインバース（b接点）"""
        self.program.LDI(device)
        return self
    
    def LDP(self, device: str) -> 'GXLadder':
        """ロードパルス（立上りエッジ）"""
        # 内部でパルス変換
        self.program.LD(device)
        return self
    
    def LDF(self, device: str) -> 'GXLadder':
        """ロードパルス（立下りエッジ）"""
        self.program.LD(device)
        return self
    
    def AND(self, device: str) -> 'GXLadder':
        """アンド（a接点直列）"""
        self.program.AND(device)
        return self
    
    def ANI(self, device: str) -> 'GXLadder':
        """アンドインバース（b接点直列）"""
        self.program.ANI(device)
        return self
    
    def ANDP(self, device: str) -> 'GXLadder':
        """アンドパルス（立上りエッジ直列）"""
        self.program.AND(device)
        return self
    
    def ANDF(self, device: str) -> 'GXLadder':
        """アンドパルス（立下りエッジ直列）"""
        self.program.AND(device)
        return self
    
    def OR(self, device: str) -> 'GXLadder':
        """オア（a接点並列）"""
        self.program.OR(device)
        return self
    
    def ORI(self, device: str) -> 'GXLadder':
        """オアインバース（b接点並列）"""
        self.program.ORI(device)
        return self
    
    def ORP(self, device: str) -> 'GXLadder':
        """オアパルス（立上りエッジ並列）"""
        self.program.OR(device)
        return self
    
    def ORF(self, device: str) -> 'GXLadder':
        """オアパルス（立下りエッジ並列）"""
        self.program.OR(device)
        return self
    
    # === 接続命令 ===
    
    def ANB(self) -> 'GXLadder':
        """アンドブロック"""
        self.program.ANB()
        return self
    
    def ORB(self) -> 'GXLadder':
        """オアブロック"""
        self.program.ORB()
        return self
    
    def MPS(self) -> 'GXLadder':
        """プッシュ"""
        self.program.MPS()
        return self
    
    def MRD(self) -> 'GXLadder':
        """リード"""
        self.program.MRD()
        return self
    
    def MPP(self) -> 'GXLadder':
        """ポップ"""
        self.program.MPP()
        return self
    
    # === 出力命令 ===
    
    def OUT(self, device: str) -> 'GXLadder':
        """出力"""
        self.program.OUT(device)
        return self
    
    def SET(self, device: str) -> 'GXLadder':
        """セット"""
        self.program.SET(device)
        return self
    
    def RST(self, device: str) -> 'GXLadder':
        """リセット"""
        self.program.RST(device)
        return self
    
    def PLS(self, device: str) -> 'GXLadder':
        """パルス（立上り）"""
        self.program.PLS(device)
        return self
    
    def PLF(self, device: str) -> 'GXLadder':
        """パルス（立下り）"""
        self.program.PLF(device)
        return self
    
    # === タイマ・カウンタ（GX Works2形式） ===
    
    def OUT_T(self, timer: str, value: str) -> 'GXLadder':
        """
        タイマ出力（GX Works2形式）
        
        例: OUT_T("T0", "K20")  # T0, 2秒
        """
        timer = timer.upper()
        if timer.startswith('T'):
            timer_no = int(timer[1:])
        else:
            timer_no = int(timer)
        
        set_value = self._parse_constant(value)
        if isinstance(set_value, str):
            set_value = 10  # デフォルト
        
        self.program.OUT_T(timer_no, set_value)
        return self
    
    def OUT_C(self, counter: str, value: str) -> 'GXLadder':
        """
        カウンタ出力（GX Works2形式）
        
        例: OUT_C("C0", "K5")  # C0, 5カウント
        """
        counter = counter.upper()
        if counter.startswith('C'):
            counter_no = int(counter[1:])
        else:
            counter_no = int(counter)
        
        set_value = self._parse_constant(value)
        if isinstance(set_value, str):
            set_value = 10
        
        self.program.OUT_C(counter_no, set_value)
        return self
    
    def RST_T(self, timer: str) -> 'GXLadder':
        """タイマリセット"""
        timer = timer.upper()
        if timer.startswith('T'):
            timer_no = int(timer[1:])
        else:
            timer_no = int(timer)
        self.program.RST_T(timer_no)
        return self
    
    def RST_C(self, counter: str) -> 'GXLadder':
        """カウンタリセット"""
        counter = counter.upper()
        if counter.startswith('C'):
            counter_no = int(counter[1:])
        else:
            counter_no = int(counter)
        self.program.RST_C(counter_no)
        return self
    
    # === 転送命令（GX Works2形式） ===
    
    def MOV(self, src: str, dest: str) -> 'GXLadder':
        """
        転送（16ビット）
        
        例: MOV("K100", "D0")  # D0 = 100
            MOV("D0", "D1")    # D1 = D0
        """
        src_val = self._parse_constant(src)
        self.program.MOV(src_val, dest)
        return self
    
    def DMOV(self, src: str, dest: str) -> 'GXLadder':
        """転送（32ビット）"""
        src_val = self._parse_constant(src)
        self.program.MOV(src_val, dest)
        return self
    
    # === 演算命令（GX Works2形式） ===
    
    def ADD(self, src1: str, src2: str, dest: str) -> 'GXLadder':
        """
        加算（16ビット）
        
        例: ADD("D0", "D1", "D2")  # D2 = D0 + D1
            ADD("D0", "K10", "D1") # D1 = D0 + 10
        """
        s1 = self._parse_constant(src1)
        s2 = self._parse_constant(src2)
        self.program.ADD(s1, s2, dest)
        return self
    
    def SUB(self, src1: str, src2: str, dest: str) -> 'GXLadder':
        """減算（16ビット）"""
        s1 = self._parse_constant(src1)
        s2 = self._parse_constant(src2)
        self.program.SUB(s1, s2, dest)
        return self
    
    def MUL(self, src1: str, src2: str, dest: str) -> 'GXLadder':
        """乗算（16ビット）"""
        s1 = self._parse_constant(src1)
        s2 = self._parse_constant(src2)
        self.program.MUL(s1, s2, dest)
        return self
    
    def DIV(self, src1: str, src2: str, dest: str) -> 'GXLadder':
        """除算（16ビット）"""
        s1 = self._parse_constant(src1)
        s2 = self._parse_constant(src2)
        self.program.DIV(s1, s2, dest)
        return self
    
    def INC(self, device: str) -> 'GXLadder':
        """インクリメント"""
        self.program.ADD(device, 1, device)
        return self
    
    def DEC(self, device: str) -> 'GXLadder':
        """デクリメント"""
        self.program.SUB(device, 1, device)
        return self
    
    # === 制御命令 ===
    
    def END(self) -> 'GXLadder':
        """終了"""
        self.program.END()
        return self
    
    def NOP(self) -> 'GXLadder':
        """無処理"""
        self.program.NOP()
        return self
    
    # === プログラム取得 ===
    
    def get_program(self) -> LadderProgram:
        """LadderProgramを取得"""
        return self.program
    
    def __str__(self) -> str:
        lines = [f"=== GX Ladder: {self.name} ==="]
        
        if self.network_comments:
            lines.append("\n[Network Comments]")
            for no, comment in sorted(self.network_comments.items()):
                lines.append(f"  N{no}: {comment}")
        
        if self.device_comments:
            lines.append("\n[Device Comments]")
            for device, comment in self.device_comments.items():
                lines.append(f"  {device}: {comment}")
        
        lines.append("\n[Instructions]")
        lines.append(str(self.program))
        
        return '\n'.join(lines)


class GXProjectLoader:
    """
    GX Works2プロジェクトローダー
    
    GX Works2からエクスポートしたテキスト形式のラダーを読み込み
    （完全な互換性はありませんが、基本的な命令をサポート）
    """
    
    # サポートする命令
    SUPPORTED_INSTRUCTIONS = {
        'LD', 'LDI', 'LDP', 'LDF',
        'AND', 'ANI', 'ANDP', 'ANDF',
        'OR', 'ORI', 'ORP', 'ORF',
        'ANB', 'ORB', 'MPS', 'MRD', 'MPP',
        'OUT', 'SET', 'RST', 'PLS', 'PLF',
        'MOV', 'DMOV', 'ADD', 'SUB', 'MUL', 'DIV',
        'INC', 'DEC', 'END', 'NOP'
    }
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def load_from_text(self, text: str, name: str = "Imported") -> Optional[GXLadder]:
        """
        テキスト形式のラダープログラムを読み込み
        
        形式例:
            ; コメント
            NETWORK 1 "自己保持回路"
            LD X0
            OR Y0
            ANI X1
            OUT Y0
            
            NETWORK 2 "タイマ回路"
            LD X2
            OUT T0 K20
            LD T0
            OUT Y1
            
            END
        """
        self.errors.clear()
        self.warnings.clear()
        
        ladder = GXLadder(name)
        lines = text.strip().split('\n')
        
        for line_no, line in enumerate(lines, 1):
            line = line.strip()
            
            # 空行・コメント行をスキップ
            if not line or line.startswith(';') or line.startswith('//'):
                continue
            
            try:
                self._parse_line(ladder, line, line_no)
            except Exception as e:
                self.errors.append(f"Line {line_no}: {e}")
        
        return ladder if not self.errors else None
    
    def load_from_file(self, filepath: str) -> Optional[GXLadder]:
        """ファイルからラダープログラムを読み込み"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
            
            name = os.path.splitext(os.path.basename(filepath))[0]
            return self.load_from_text(text, name)
            
        except Exception as e:
            self.errors.append(f"File error: {e}")
            return None
    
    def _parse_line(self, ladder: GXLadder, line: str, line_no: int):
        """1行を解析"""
        # ネットワーク宣言
        if line.upper().startswith('NETWORK'):
            match = re.match(r'NETWORK\s+(\d+)\s*(?:"([^"]*)")?', line, re.IGNORECASE)
            if match:
                no = int(match.group(1))
                comment = match.group(2) or ""
                ladder.network(no, comment)
            return
        
        # デバイスコメント
        if line.upper().startswith('COMMENT'):
            match = re.match(r'COMMENT\s+(\w+)\s+"([^"]*)"', line, re.IGNORECASE)
            if match:
                device = match.group(1)
                comment = match.group(2)
                ladder.comment(device, comment)
            return
        
        # 命令を解析
        parts = line.split()
        if not parts:
            return
        
        instruction = parts[0].upper()
        operands = parts[1:]
        
        # 命令を実行
        if instruction == 'LD':
            ladder.LD(operands[0])
        elif instruction == 'LDI':
            ladder.LDI(operands[0])
        elif instruction == 'LDP':
            ladder.LDP(operands[0])
        elif instruction == 'LDF':
            ladder.LDF(operands[0])
        elif instruction == 'AND':
            ladder.AND(operands[0])
        elif instruction == 'ANI':
            ladder.ANI(operands[0])
        elif instruction == 'ANDP':
            ladder.ANDP(operands[0])
        elif instruction == 'ANDF':
            ladder.ANDF(operands[0])
        elif instruction == 'OR':
            ladder.OR(operands[0])
        elif instruction == 'ORI':
            ladder.ORI(operands[0])
        elif instruction == 'ORP':
            ladder.ORP(operands[0])
        elif instruction == 'ORF':
            ladder.ORF(operands[0])
        elif instruction == 'ANB':
            ladder.ANB()
        elif instruction == 'ORB':
            ladder.ORB()
        elif instruction == 'MPS':
            ladder.MPS()
        elif instruction == 'MRD':
            ladder.MRD()
        elif instruction == 'MPP':
            ladder.MPP()
        elif instruction == 'OUT':
            if operands[0].upper().startswith('T') and len(operands) >= 2:
                ladder.OUT_T(operands[0], operands[1])
            elif operands[0].upper().startswith('C') and len(operands) >= 2:
                ladder.OUT_C(operands[0], operands[1])
            else:
                ladder.OUT(operands[0])
        elif instruction == 'SET':
            ladder.SET(operands[0])
        elif instruction == 'RST':
            if operands[0].upper().startswith('T'):
                ladder.RST_T(operands[0])
            elif operands[0].upper().startswith('C'):
                ladder.RST_C(operands[0])
            else:
                ladder.RST(operands[0])
        elif instruction == 'PLS':
            ladder.PLS(operands[0])
        elif instruction == 'PLF':
            ladder.PLF(operands[0])
        elif instruction == 'MOV':
            ladder.MOV(operands[0], operands[1])
        elif instruction == 'DMOV':
            ladder.DMOV(operands[0], operands[1])
        elif instruction == 'ADD':
            ladder.ADD(operands[0], operands[1], operands[2])
        elif instruction == 'SUB':
            ladder.SUB(operands[0], operands[1], operands[2])
        elif instruction == 'MUL':
            ladder.MUL(operands[0], operands[1], operands[2])
        elif instruction == 'DIV':
            ladder.DIV(operands[0], operands[1], operands[2])
        elif instruction == 'INC':
            ladder.INC(operands[0])
        elif instruction == 'DEC':
            ladder.DEC(operands[0])
        elif instruction == 'END':
            ladder.END()
        elif instruction == 'NOP':
            ladder.NOP()
        else:
            self.warnings.append(f"Line {line_no}: Unknown instruction '{instruction}'")


# === サンプルプログラム（GX Works2形式） ===

def create_gx_sample_1() -> GXLadder:
    """
    サンプル1: 自己保持回路
    
    GX Works2形式で記述
    """
    ladder = GXLadder("自己保持回路")
    
    # デバイスコメント
    ladder.comment("X0", "起動スイッチ")
    ladder.comment("X1", "停止スイッチ")
    ladder.comment("Y0", "出力ランプ")
    
    # ネットワーク1: 自己保持
    ladder.network(1, "自己保持回路")
    ladder.LD("X0")
    ladder.OR("Y0")
    ladder.ANI("X1")
    ladder.OUT("Y0")
    
    ladder.END()
    
    return ladder


def create_gx_sample_2() -> GXLadder:
    """
    サンプル2: タイマ回路
    """
    ladder = GXLadder("タイマ回路")
    
    ladder.comment("X0", "タイマ起動")
    ladder.comment("T0", "オンディレイタイマ")
    ladder.comment("Y0", "タイマ出力")
    
    # ネットワーク1: タイマ
    ladder.network(1, "2秒タイマ")
    ladder.LD("X0")
    ladder.OUT_T("T0", "K20")  # 2秒
    
    # ネットワーク2: タイマ接点で出力
    ladder.network(2, "タイマ接点出力")
    ladder.LD("T0")
    ladder.OUT("Y0")
    
    ladder.END()
    
    return ladder


def create_gx_sample_3() -> GXLadder:
    """
    サンプル3: カウンタ回路
    """
    ladder = GXLadder("カウンタ回路")
    
    ladder.comment("X0", "カウント入力")
    ladder.comment("X1", "リセット")
    ladder.comment("C0", "アップカウンタ")
    ladder.comment("Y0", "カウント完了")
    
    # ネットワーク1: カウンタ
    ladder.network(1, "5カウント")
    ladder.LD("X0")
    ladder.OUT_C("C0", "K5")
    
    # ネットワーク2: カウンタ接点
    ladder.network(2, "カウント完了出力")
    ladder.LD("C0")
    ladder.OUT("Y0")
    
    # ネットワーク3: リセット
    ladder.network(3, "カウンタリセット")
    ladder.LD("X1")
    ladder.RST_C("C0")
    
    ladder.END()
    
    return ladder


def create_gx_sample_4() -> GXLadder:
    """
    サンプル4: データ演算
    """
    ladder = GXLadder("データ演算")
    
    ladder.comment("M0", "演算実行")
    ladder.comment("D0", "入力値1")
    ladder.comment("D1", "入力値2")
    ladder.comment("D10", "加算結果")
    ladder.comment("D11", "減算結果")
    ladder.comment("D12", "乗算結果")
    ladder.comment("D13", "除算結果")
    
    # ネットワーク1: 初期値設定
    ladder.network(1, "初期値設定")
    ladder.LD("M100")  # 常時ON（SM400相当）
    ladder.MOV("K100", "D0")
    ladder.MOV("K25", "D1")
    
    # ネットワーク2: 四則演算
    ladder.network(2, "四則演算")
    ladder.LD("M0")
    ladder.ADD("D0", "D1", "D10")  # D10 = D0 + D1
    ladder.LD("M0")
    ladder.SUB("D0", "D1", "D11")  # D11 = D0 - D1
    ladder.LD("M0")
    ladder.MUL("D0", "D1", "D12")  # D12 = D0 * D1
    ladder.LD("M0")
    ladder.DIV("D0", "D1", "D13")  # D13 = D0 / D1
    
    ladder.END()
    
    return ladder


def create_gx_sample_5() -> GXLadder:
    """
    サンプル5: 複雑条件回路
    """
    ladder = GXLadder("複雑条件")
    
    ladder.comment("X0", "条件A1")
    ladder.comment("X1", "条件A2")
    ladder.comment("X2", "条件B1")
    ladder.comment("X3", "条件B2")
    ladder.comment("Y0", "結果出力")
    
    # (X0 AND X1) OR (X2 AND X3) → Y0
    ladder.network(1, "(X0 AND X1) OR (X2 AND X3)")
    ladder.LD("X0")
    ladder.AND("X1")
    ladder.LD("X2")
    ladder.AND("X3")
    ladder.ORB()
    ladder.OUT("Y0")
    
    ladder.END()
    
    return ladder


# === ラダーテキストのサンプル ===

SAMPLE_LADDER_TEXT = """; サンプルラダープログラム
; GX Works2エクスポート形式（簡易版）

COMMENT X0 "起動スイッチ"
COMMENT X1 "停止スイッチ"
COMMENT Y0 "出力ランプ"

NETWORK 1 "自己保持回路"
LD X0
OR Y0
ANI X1
OUT Y0

NETWORK 2 "タイマ回路"
LD X2
OUT T0 K20
LD T0
OUT Y1

NETWORK 3 "カウンタ回路"
LD X3
OUT C0 K5
LD C0
OUT Y2
LD X4
RST C0

END
"""
