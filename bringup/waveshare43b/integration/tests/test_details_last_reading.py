from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class DetailsLastReading(unittest.TestCase):
    def test_related_deltas_retain_readings_but_silence_and_offline_show_age(self):
        source = (ROOT / 'src/display_ws43b.cpp').read_text()
        functions = source[source.index('template <class Field>\nconst char *missing'):source.index('void temperature(')]
        functions += source[source.index('void detailCard('):source.index('void levelCard(')]
        functions += source[source.index('template<class Field>\nvoid amsReadingAge'):source.index('void amsView(')]
        functions += source[source.index('// Match the dashboard/AMS policy:'):source.index('void settingRow(')]
        code = r'''
#include "bambu_monitor_parser.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using String=std::string;
constexpr int CARD=1,INK=2,DIM=3,WARN=4,ACCENT=5,TRACK=6;
constexpr int ws43b_dash_14=14,ws43b_dash_18=18,ws43b_dash_30=30;
const char* ws43bText(const char* pl,const char*){return pl;}
struct {bool fanMatchPrinter=false;} dispSettings;
struct Text{std::string value;int x,y,color;};std::vector<Text> texts;
struct Bar{int x,y,w,h,color;};std::vector<Bar> bars;
void dashText(const char*s,int x,int y,int,int,int color){texts.push_back({s,x,y,color});}
void button(const char*,int,int,int,int,bool){}
struct Canvas {
 template<class... A>void fillRoundRect(A...){}
 void fillRect(int x,int y,int w,int h,int color){bars.push_back({x,y,w,h,color});}
 void loadFont(int){}void unloadFont(){}
 int textWidth(const char*s){return strlen(s)*9;}
}tft;
''' + functions + r'''
bool at(int x,int y,const char*s,int color){for(auto &t:texts)if(t.x==x&&t.y==y&&t.value==s&&t.color==color)return true;return false;}
bool contains(const char*s){for(auto &t:texts)if(t.value.find(s)!=std::string::npos)return true;return false;}
void draw(const BambuMonitorTelemetry&m,bool online,uint32_t now){texts.clear();bars.clear();detailsScreen(m,online,now);}
void report(BambuMonitorTelemetry&m,const char*s,uint32_t now){assert(bambu_monitor::parse((const uint8_t*)s,strlen(s),m,now));}
int main(){
 BambuMonitorTelemetry m;
 report(m,R"({"print":{"subtask_name":"Test","layer_num":14,"total_layer_num":89,"chamber_temper":24,"spd_lvl":2,"fan_gear":8421631}})",100);
 draw(m,true,100);
 assert(at(552,257,"Standard",INK)&&at(296,257,"24°C",INK)&&at(40,365,"100%",INK));
 assert(!contains("temu"));
 // A later core delta retains omitted values without rewriting their ages.
 // Displayed values remain current; real silence/offline still labels history.
 report(m,R"({"print":{"chamber_temper":25,"layer_num":15}})",180100);
 draw(m,true,180100);
 assert(at(552,257,"Standard",INK)&&at(296,257,"25°C",INK)&&at(40,365,"100%",INK));
 assert(!contains("temu")&&!contains("Nieaktualne"));
 assert(m.speedLevel.updatedMs==100&&m.partFanPct.updatedMs==100&&!m.partFanPct.fresh(180100));
 for(auto &b:bars){assert(b.y==417&&b.h==3&&b.color==ACCENT);}
 // Offline is explicit even for a recently received reading.
 draw(m,false,180100);
 assert(at(296,257,"25°C",DIM)&&at(296,291,"0 s temu · offline",WARN));
 assert(at(40,399,"3 min temu · offline",WARN));
 // Zero is a real reading; current bars are bright. Both fan display modes
 // use the same validity/age decision, with the printer-rounded value intact.
 report(m,R"({"print":{"fan_gear":128,"chamber_temper":0}})",180101);
 draw(m,true,180101);assert(at(40,365,"50%",INK)&&at(296,365,"0%",INK)&&at(296,257,"0°C",INK));
 assert(bars.size()==1&&bars[0].color==ACCENT);
 dispSettings.fanMatchPrinter=true;m.partFanRoundedPct=40;
 draw(m,true,250101);assert(at(40,365,"40%",DIM)&&at(40,399,"1 min temu",WARN));
 // Explicit invalidation and a new MQTT session must never reveal old values.
 m.speedLevel.invalidate(250102);m.partFanPct.invalidate(250102);m.chamberTemp.invalidate(250102);
 draw(m,true,250102);
 assert(at(552,257,"Brak danych",DIM)&&at(40,365,"Brak danych",DIM)&&at(296,257,"Brak danych",DIM));
 assert(!contains("Standard")&&!contains("40%"));
 m.newSession();draw(m,true,250103);assert(bars.empty()&&!contains("temu")&&!contains("Standard"));
 // Age arithmetic remains valid over millis() rollover.
 m.speedLevel.set(2,0xffffff00u);draw(m,true,0x100u);assert(at(552,257,"Standard",INK)&&!contains("temu"));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'test.cpp').write_text(code)
            subprocess.run([
                'clang++', '-std=c++17', '-Wno-deprecated-declarations',
                '-I', str(ROOT / 'include'), '-I', str(ROOT / 'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3/src'),
                str(p / 'test.cpp'), '-o', str(p / 'test')], check=True, capture_output=True)
            result = subprocess.run([str(p / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
