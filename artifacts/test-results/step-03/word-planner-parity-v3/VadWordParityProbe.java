import java.nio.file.*;
import java.util.*;
import org.json.*;
import ru.replika.domain.*;

public class VadWordParityProbe {
 public static void main(String[] args) throws Exception {
  JSONArray input=new JSONArray(Files.readString(Path.of(args[0])));
  JSONArray output=new JSONArray();
  for(int index=0;index<input.length();index++) {
   JSONObject item=input.getJSONObject(index);
   List<String> tokens=new ArrayList<>();JSONArray tokenArray=item.getJSONArray("tokens");
   for(int i=0;i<tokenArray.length();i++) tokens.add(tokenArray.getString(i));
   JSONArray timestampArray=item.getJSONArray("timestamps");float[] times=new float[timestampArray.length()];
   for(int i=0;i<times.length;i++) times[i]=(float)timestampArray.getDouble(i);
   List<Turn> turns=new ArrayList<>();JSONArray turnArray=item.getJSONArray("turns");
   for(int i=0;i<turnArray.length();i++) {JSONObject t=turnArray.getJSONObject(i);turns.add(new Turn(t.getLong("startMs"),t.getLong("endMs"),t.getInt("speakerId")));}
   VadWordPlanner.WordResult parsed=VadWordPlanner.INSTANCE.words(item.getString("text"),tokens,times,new Span(item.getLong("start_ms"),item.getLong("end_ms")),40);
   JSONObject row=new JSONObject().put("id",item.getString("id")).put("supported",parsed.getSupported()).put("reason",parsed.getReason());
   JSONArray words=new JSONArray();
   for(VadWordPlanner.Word w:parsed.getWords()) words.put(new JSONObject().put("start_ms",w.getStartMs()).put("end_ms",w.getEndMs()).put("text",w.getText()).put("reasons",w.getReasons()));
   row.put("words",words);
   if(parsed.getSupported()) {
    List<VadWordPlanner.AssignedWord> assigned=VadWordPlanner.INSTANCE.assignWords(parsed.getWords(),turns);
    JSONArray assignedJson=new JSONArray();
    for(VadWordPlanner.AssignedWord w:assigned) assignedJson.put(new JSONObject().put("start_ms",w.getStartMs()).put("end_ms",w.getEndMs()).put("text",w.getText()).put("speaker",w.getSpeaker()).put("reasons",w.getReasons()));
    row.put("assigned",assignedJson);
    for(boolean seam:new boolean[]{false,true}) {
     JSONArray grouped=new JSONArray();
     for(Segment s:VadWordPlanner.INSTANCE.groupWords(assigned,"Model parity fixture",seam)) grouped.put(new JSONObject().put("startMs",s.getStartMs()).put("endMs",s.getEndMs()).put("speakerId",s.getSpeakerId()).put("text",s.getText()).put("source",s.getSource()).put("warnings",s.getReasons()));
     row.put(seam?"groups_seam":"groups_none",grouped);
    }
   }
   output.put(row);
  }
  Files.writeString(Path.of(args[1]),output.toString());
 }
}