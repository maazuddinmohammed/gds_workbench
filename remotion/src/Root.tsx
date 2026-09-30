import "./index.css";
import { Composition, Folder } from "remotion";
import { staticFile } from "remotion";
import { loadFont } from "@remotion/fonts";
import { Reveal } from "./scenes/Reveal";
import { Metadata } from "./scenes/Metadata";
import { Models } from "./scenes/Models";
import { Code } from "./scenes/Code";
import { Review } from "./scenes/Review";
import { Close } from "./scenes/Close";
import { AtlasLaunch } from "./AtlasLaunch";

loadFont({
  family: "Manrope",
  url: staticFile("fonts/manrope.woff2"),
  weight: "200 800",
});

export const RemotionRoot = () => (
  <>
    <Composition
      id="AtlasLaunch"
      component={AtlasLaunch}
      durationInFrames={1200}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ soundtrack: true }}
    />
    <Folder name="Scenes">
      <Composition
        id="Reveal"
        component={Reveal}
        durationInFrames={180}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="Metadata"
        component={Metadata}
        durationInFrames={210}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="Models"
        component={Models}
        durationInFrames={240}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="Code"
        component={Code}
        durationInFrames={240}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="Review"
        component={Review}
        durationInFrames={210}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="Close"
        component={Close}
        durationInFrames={180}
        fps={30}
        width={1920}
        height={1080}
      />
    </Folder>
  </>
);
