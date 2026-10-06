import { Composition, Folder } from "remotion";
import { AtlasFilm, makeScenePreview } from "./atlas-film/AtlasFilm";
import { SCENES, TOTAL_FRAMES } from "./atlas-film/timeline";
import {
  MeetAtlas,
  AtlasIdentity,
  GdsFoundation,
  AtlasModeling,
  WorkspaceTour,
  LogicalRunDemo,
  ExportArtifacts,
  DeliveryHandoff,
  PluginLifecycle,
  Safeguards,
  LaunchClosing,
  COMPLETE_SECONDS,
} from "./launch-next/MeetAtlas";
import { AtlasLaunch } from "./AtlasLaunch";
import { Opening } from "./scenes/Opening";
import { Sources } from "./scenes/Sources";
import { Ingestion } from "./scenes/Ingestion";
import { Scope } from "./scenes/Scope";
import { Evidence } from "./scenes/Evidence";
import { Models } from "./scenes/Models";
import { Mapping } from "./scenes/Mapping";
import { Code } from "./scenes/Code";
import { Execution } from "./scenes/Execution";
import { Investigate } from "./scenes/Investigate";
import { Evolve } from "./scenes/Evolve";
import { Closing } from "./scenes/Closing";

export const RemotionRoot = () => (
  <>
    <Composition
      id="Atlas-Film"
      component={AtlasFilm}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={TOTAL_FRAMES}
      defaultProps={{ musicVolume: 0.75 }}
    />
    <Folder name="Atlas-Film-Scenes">
      {SCENES.map((s, i) => (
        <Composition
          key={s.id}
          id={`Film-${String(i + 1).padStart(2, "0")}-${s.id}`}
          component={makeScenePreview(s.id)}
          width={1920}
          height={1080}
          fps={30}
          durationInFrames={s.frames}
        />
      ))}
    </Folder>
    <Composition
      id="Meet-Atlas"
      component={MeetAtlas}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={COMPLETE_SECONDS * 30}
    />
    <Folder name="Meet-Atlas-Beats">
      <Composition
        id="Meet-Atlas-Identity"
        component={AtlasIdentity}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={210}
      />
      <Composition
        id="Meet-Atlas-Foundation"
        component={GdsFoundation}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={1530}
      />
      <Composition
        id="Meet-Atlas-Modeling"
        component={AtlasModeling}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={960}
      />
      <Composition
        id="Meet-Atlas-App"
        component={WorkspaceTour}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={840}
      />
      <Composition
        id="Meet-Atlas-Logical-Run"
        component={LogicalRunDemo}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={45 * 30}
      />
      <Composition
        id="Meet-Atlas-Exports"
        component={ExportArtifacts}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={14 * 30}
      />
      <Composition
        id="Meet-Atlas-Plugin-Lifecycle"
        component={PluginLifecycle}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={36 * 30}
      />
      <Composition
        id="Meet-Atlas-Safeguards"
        component={Safeguards}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={22 * 30}
      />
      <Composition
        id="Meet-Atlas-Closing"
        component={LaunchClosing}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={8 * 30}
      />
      <Composition
        id="Meet-Atlas-Delivery"
        component={DeliveryHandoff}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={18 * 30}
      />
    </Folder>
    <Composition
      id="Atlas-Launch"
      component={AtlasLaunch}
      width={1920}
      height={1080}
      fps={30}
      durationInFrames={4680}
      defaultProps={{ musicVolume: 0.8 }}
    />
    <Folder name="Scenes">
      <Composition
        id="01-Meet-Atlas"
        component={Opening}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={240}
      />
      <Composition
        id="02-Source-Landscape"
        component={Sources}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={480}
      />
      <Composition
        id="03-Metadata-Ingestion"
        component={Ingestion}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={360}
      />
      <Composition
        id="04-Model-Scope"
        component={Scope}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={390}
      />
      <Composition
        id="05-Evidence"
        component={Evidence}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={720}
      />
      <Composition
        id="06-Common-Models"
        component={Models}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={450}
      />
      <Composition
        id="07-Mapping"
        component={Mapping}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={330}
      />
      <Composition
        id="08-SQL-Validation"
        component={Code}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={360}
      />
      <Composition
        id="09-Orchestration"
        component={Execution}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={390}
      />
      <Composition
        id="10-Investigate"
        component={Investigate}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={300}
      />
      <Composition
        id="11-Evolve"
        component={Evolve}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={420}
      />
      <Composition
        id="12-Complete-Lifecycle"
        component={Closing}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={240}
      />
    </Folder>
  </>
);
