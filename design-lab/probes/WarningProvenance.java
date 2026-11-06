import java.util.*;
import ru.replika.domain.*;
import ru.replika.data.SegmentRow;
import ru.replika.ui.SmartReviewKt;
import org.json.*;

/** Calls existing compiled V1.3 production classes. Does not change Android sources. */
public class WarningProvenance {
 public static void main(String[] args) {
  var slices=RecognitionPlanner.INSTANCE.plan(List.of(new Span(0,6000)),List.of(new Turn(200,6000,0)),20000);
  if(slices.size()!=1) throw new AssertionError(slices);
  var s=slices.get(0);
  var row=new SegmentRow("probe","probe",s.getStartMs(),s.getEndMs(),s.getSpeaker(),"Контролируемая реплика","fixture",false,new JSONArray(s.getReasons()).toString(),false);
  var issues=SmartReviewKt.reviewIssues(row);
  if(s.getEndMs()-s.getStartMs()!=6000 || !issues.get(0).getExplanation().contains("700")) throw new AssertionError(issues);
  System.out.println(new JSONObject().put("productionClasses","unmodified compiled V1.3").put("inputVad",new JSONArray(List.of(0,6000))).put("inputDiarization",new JSONArray(List.of(200,6000,0))).put("outputSliceMs",new JSONArray(List.of(s.getStartMs(),s.getEndMs()))).put("reasons",new JSONArray(s.getReasons())).put("uiTitle",issues.get(0).getTitle()).put("uiExplanation",issues.get(0).getExplanation()).put("mismatchReproduced",true).put("userRecordingReproduced",false).toString(2));
 }
}
