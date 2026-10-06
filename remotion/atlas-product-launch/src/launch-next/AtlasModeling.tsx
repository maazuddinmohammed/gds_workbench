import {
  CanvasImage,
  Interactive,
  interpolate,
  interpolateColors,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, Icon, Logo } from "../design";
import { Arrow, motion, SplitStage, StoryCopy } from "./MeetLayout";

/** Keep the lakehouse and Atlas present as a selected scope becomes shared models. */
export const AtlasModeling = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <SplitStage
      copy={
        <>
          <StoryCopy
            name="Define the model scope"
            label="DEFINE THE SCOPE"
            title={"Define\nyour scope."}
            at={2}
            until={9}
          >
            Select Bronze tables from
            <br />
            the metadata within Atlas.
          </StoryCopy>
          <StoryCopy
            name="Understand the selected scope"
            label="UNDERSTAND THE SCOPE"
            title={"Understand\nthe scope."}
            at={9.5}
            until={20}
          >
            <span
              style={{
                color: interpolateColors(
                  f,
                  [10 * fps, 10.8 * fps, 12.5 * fps, 13 * fps],
                  [C.muted, C.green, C.green, C.muted],
                ),
              }}
            >
              Profile
            </span>
            {", "}
            <span
              style={{
                color: interpolateColors(
                  f,
                  [13 * fps, 13.8 * fps, 15.5 * fps, 16 * fps],
                  [C.muted, C.accent, C.accent, C.muted],
                ),
              }}
            >
              enrich
            </span>
            {" and "}
            <span
              style={{
                color: interpolateColors(
                  f,
                  [16 * fps, 16.8 * fps, 19 * fps, 19.5 * fps],
                  [C.muted, "#456E96", "#456E96", C.muted],
                ),
              }}
            >
              analyze
            </span>
            <br />
            the selected data.
          </StoryCopy>
          <StoryCopy
            name="Build the operational data model"
            label="OPERATIONAL DATA MODEL"
            title={"A common\noperational model."}
            at={21}
            until={26}
          >
            Design toward third normal form.
          </StoryCopy>
          <StoryCopy
            name="Build the dimensional data model"
            label="DIMENSIONAL DATA MODEL"
            title={"Model for\nanalytics."}
            at={27}
            until={32.4}
          >
            Build analytics on the applied
            <br />
            operational model.
          </StoryCopy>
        </>
      }
    >
      <Interactive.Div
        name="Boxed Databricks Lakehouse Bronze input"
        style={{
          position: "absolute",
          left: 20,
          top: 210,
          width: 235,
          height: 285,
          borderRadius: 26,
          border: "2px solid #D3C5B7",
          background: C.white,
          padding: "21px 18px",
          boxSizing: "border-box",
          textAlign: "center",
          opacity: interpolate(f, [0, 0.8 * fps], [0, 1], motion),
        }}
      >
        <CanvasImage
          src={staticFile("brands/databricks.svg")}
          style={{ width: 50, height: 54 }}
        />
        <div style={{ fontSize: 26, fontWeight: 600, marginTop: 7 }}>
          Databricks
        </div>
        <div style={{ fontSize: 30, fontWeight: 600, marginTop: 2 }}>
          Lakehouse
        </div>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 166,
            height: 1,
            background: "#D3C5B7",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 20,
            right: 20,
            top: 185,
            height: 50,
            lineHeight: "46px",
            boxSizing: "border-box",
            fontSize: 28,
            fontWeight: 600,
            borderRadius: 11,
            border: "2px solid #B88A5B",
            background: "#F0DFD1",
          }}
        >
          Bronze
        </div>
      </Interactive.Div>
      <Arrow d="M274 420H312" at={1} until={32.5} color={C.green} />
      <Interactive.Div
        name="Persistent Atlas modeling workspace"
        style={{
          position: "absolute",
          left: 330,
          top: 45,
          width: 700,
          height: 610,
          borderRadius: 28,
          border: "2px solid " + C.line,
          background: C.white,
          boxSizing: "border-box",
          opacity: interpolate(f, [0.3 * fps, 1.3 * fps], [0, 1], motion),
        }}
      >
        <div style={{ position: "absolute", left: 38, top: 31 }}>
          <Logo size={52} />
        </div>
        <div
          style={{
            position: "absolute",
            left: 38,
            right: 38,
            top: 95,
            height: 1,
            background: C.line,
          }}
        />
      </Interactive.Div>

      <Interactive.Div
        name="Select Bronze metadata tables for the model scope"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [1 * fps, 2 * fps, 8.3 * fps, 9 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 370,
            top: 160,
            fontSize: 34,
            fontWeight: 700,
          }}
        >
          Define Scope
        </div>
        <div
          style={{
            position: "absolute",
            left: 370,
            top: 210,
            fontSize: 26,
            color: C.muted,
          }}
        >
          Metadata · Bronze tables
        </div>
        <div
          style={{
            position: "absolute",
            right: 60,
            top: 168,
            fontSize: 26,
            color: C.muted,
          }}
        >
          CustomerOrders360
        </div>
        <Interactive.Div
          name="Select Customers in scope"
          style={{
            position: "absolute",
            left: 370,
            top: 255,
            width: 620,
            height: 90,
            padding: "0 25px",
            boxSizing: "border-box",
            display: "flex",
            alignItems: "center",
            gap: 20,
            borderRadius: 15,
            border: "2px solid",
            borderColor: interpolateColors(
              f,
              [2.8 * fps, 3.6 * fps],
              [C.line, C.green],
            ),
            background: interpolateColors(
              f,
              [2.8 * fps, 3.6 * fps],
              [C.white, "#EEF3EA"],
            ),
          }}
        >
          <Icon kind="database" size={40} color={C.green} />
          <div style={{ fontSize: 32 }}>Customers</div>
          <div
            style={{
              marginLeft: "auto",
              width: 38,
              height: 38,
              borderRadius: 10,
              border: "2px solid " + C.line,
              background: interpolateColors(
                f,
                [2.8 * fps, 3.6 * fps],
                [C.white, C.green],
              ),
            }}
          >
            <div
              style={{
                opacity: interpolate(f, [2.8 * fps, 3.6 * fps], [0, 1], motion),
              }}
            >
              <Icon kind="check" size={38} color={C.white} />
            </div>
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Select Orders in scope"
          style={{
            position: "absolute",
            left: 370,
            top: 365,
            width: 620,
            height: 90,
            padding: "0 25px",
            boxSizing: "border-box",
            display: "flex",
            alignItems: "center",
            gap: 20,
            borderRadius: 15,
            border: "2px solid",
            borderColor: interpolateColors(
              f,
              [4.5 * fps, 5.3 * fps],
              [C.line, C.green],
            ),
            background: interpolateColors(
              f,
              [4.5 * fps, 5.3 * fps],
              [C.white, "#EEF3EA"],
            ),
          }}
        >
          <Icon kind="database" size={40} color={C.green} />
          <div style={{ fontSize: 32 }}>Orders</div>
          <div
            style={{
              marginLeft: "auto",
              width: 38,
              height: 38,
              borderRadius: 10,
              border: "2px solid " + C.line,
              background: interpolateColors(
                f,
                [4.5 * fps, 5.3 * fps],
                [C.white, C.green],
              ),
            }}
          >
            <div
              style={{
                opacity: interpolate(f, [4.5 * fps, 5.3 * fps], [0, 1], motion),
              }}
            >
              <Icon kind="check" size={38} color={C.white} />
            </div>
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Select Products in scope"
          style={{
            position: "absolute",
            left: 370,
            top: 475,
            width: 620,
            height: 90,
            padding: "0 25px",
            boxSizing: "border-box",
            display: "flex",
            alignItems: "center",
            gap: 20,
            borderRadius: 15,
            border: "2px solid",
            borderColor: interpolateColors(
              f,
              [6.2 * fps, 7 * fps],
              [C.line, C.green],
            ),
            background: interpolateColors(
              f,
              [6.2 * fps, 7 * fps],
              [C.white, "#EEF3EA"],
            ),
          }}
        >
          <Icon kind="database" size={40} color={C.green} />
          <div style={{ fontSize: 32 }}>Products</div>
          <div
            style={{
              marginLeft: "auto",
              width: 38,
              height: 38,
              borderRadius: 10,
              border: "2px solid " + C.line,
              background: interpolateColors(
                f,
                [6.2 * fps, 7 * fps],
                [C.white, C.green],
              ),
            }}
          >
            <div
              style={{
                opacity: interpolate(f, [6.2 * fps, 7 * fps], [0, 1], motion),
              }}
            >
              <Icon kind="check" size={38} color={C.white} />
            </div>
          </div>
        </Interactive.Div>
      </Interactive.Div>

      <Interactive.Div
        name="Evidence from the selected scope"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [9 * fps, 10 * fps, 19.3 * fps, 20 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 370,
            top: 168,
            width: 620,
            fontSize: 26,
            color: C.green,
          }}
        >
          Customers · Orders · Products
        </div>
        <Interactive.Div
          name="Profile with distribution evidence"
          style={{
            position: "absolute",
            left: 370,
            top: 240,
            width: 195,
            height: 295,
            padding: "25px 20px",
            boxSizing: "border-box",
            borderRadius: 20,
            border: "2px solid",
            borderColor: interpolateColors(
              f,
              [10 * fps, 10.8 * fps, 12.5 * fps, 13 * fps],
              [C.line, C.green, C.green, C.line],
            ),
            background: interpolateColors(
              f,
              [10 * fps, 10.8 * fps, 12.5 * fps, 13 * fps],
              [C.white, "#EEF3EA", "#EEF3EA", C.white],
            ),
          }}
        >
          <div style={{ fontSize: 29, color: C.green }}>Profile</div>
          <svg
            width="150"
            height="110"
            viewBox="0 0 150 110"
            style={{ marginTop: 34 }}
          >
            <path d="M5 100H145" stroke="#B8C9B9" strokeWidth="2" />
            <rect x="13" y="58" width="22" height="40" rx="5" fill="#B8CEBB" />
            <rect x="45" y="30" width="22" height="68" rx="5" fill="#80A88A" />
            <rect x="77" y="8" width="22" height="90" rx="5" fill={C.green} />
            <rect x="109" y="44" width="22" height="54" rx="5" fill="#98B79D" />
          </svg>
          <div style={{ fontSize: 26, color: C.muted, marginTop: 27 }}>
            Patterns
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Enrich with business context"
          style={{
            position: "absolute",
            left: 582,
            top: 240,
            width: 195,
            height: 295,
            padding: "25px 20px",
            boxSizing: "border-box",
            borderRadius: 20,
            border: "2px solid",
            borderColor: interpolateColors(
              f,
              [13 * fps, 13.8 * fps, 15.5 * fps, 16 * fps],
              [C.line, C.accent, C.accent, C.line],
            ),
            background: interpolateColors(
              f,
              [13 * fps, 13.8 * fps, 15.5 * fps, 16 * fps],
              [C.white, "#F7E9DE", "#F7E9DE", C.white],
            ),
          }}
        >
          <div style={{ fontSize: 29, color: C.accent }}>Enrich</div>
          <svg
            width="150"
            height="110"
            viewBox="0 0 150 110"
            style={{ marginTop: 34 }}
          >
            <rect
              x="7"
              y="5"
              width="121"
              height="92"
              rx="10"
              fill="#FFFEFA"
              stroke="#D0AB8F"
              strokeWidth="2"
            />
            <path
              d="M24 25H92M24 42H108M24 59H75"
              stroke="#BC8D6D"
              strokeWidth="5"
              strokeLinecap="round"
            />
            <rect x="64" y="75" width="79" height="29" rx="8" fill="#E7C3A5" />
            <path
              d="M79 89H127"
              stroke={C.accent}
              strokeWidth="4"
              strokeLinecap="round"
            />
          </svg>
          <div style={{ fontSize: 26, color: C.muted, marginTop: 27 }}>
            Context
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Analyze relationships across the scope"
          style={{
            position: "absolute",
            left: 794,
            top: 240,
            width: 195,
            height: 295,
            padding: "25px 20px",
            boxSizing: "border-box",
            borderRadius: 20,
            border: "2px solid",
            borderColor: interpolateColors(
              f,
              [16 * fps, 16.8 * fps, 19 * fps, 19.5 * fps],
              [C.line, "#456E96", "#456E96", C.line],
            ),
            background: interpolateColors(
              f,
              [16 * fps, 16.8 * fps, 19 * fps, 19.5 * fps],
              [C.white, "#EAF0F6", "#EAF0F6", C.white],
            ),
          }}
        >
          <div style={{ fontSize: 29, color: "#456E96" }}>Analyze</div>
          <svg
            width="150"
            height="110"
            viewBox="0 0 150 110"
            style={{ marginTop: 34 }}
          >
            <path
              d="M75 50L25 20M75 50L126 20M75 50L25 90M75 50L126 90"
              stroke="#80A0BA"
              strokeWidth="3"
            />
            <rect
              x="4"
              y="5"
              width="42"
              height="30"
              rx="7"
              fill="#DBE6EF"
              stroke="#7495AE"
              strokeWidth="2"
            />
            <rect
              x="104"
              y="5"
              width="42"
              height="30"
              rx="7"
              fill="#DBE6EF"
              stroke="#7495AE"
              strokeWidth="2"
            />
            <rect
              x="4"
              y="75"
              width="42"
              height="30"
              rx="7"
              fill="#DBE6EF"
              stroke="#7495AE"
              strokeWidth="2"
            />
            <rect
              x="104"
              y="75"
              width="42"
              height="30"
              rx="7"
              fill="#DBE6EF"
              stroke="#7495AE"
              strokeWidth="2"
            />
            <rect x="53" y="35" width="44" height="34" rx="8" fill="#456E96" />
          </svg>
          <div style={{ fontSize: 26, color: C.muted, marginTop: 27 }}>
            Relations
          </div>
        </Interactive.Div>
      </Interactive.Div>

      <Interactive.Div
        name="Illustrative unified operational model"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(
            f,
            [20 * fps, 21 * fps, 25.3 * fps, 26 * fps],
            [0, 1, 1, 0],
            motion,
          ),
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 370,
            top: 164,
            width: 620,
            fontSize: 28,
            fontWeight: 600,
          }}
        >
          Common Operational Model · 3NF
        </div>
        <svg
          width="1050"
          height="710"
          style={{ position: "absolute", inset: 0 }}
        >
          <path
            d="M620 320H740M850 390V425H680V455"
            fill="none"
            stroke="#91AD98"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <circle cx="620" cy="320" r="5" fill={C.green} />
          <circle cx="740" cy="320" r="5" fill={C.green} />
          <circle cx="850" cy="390" r="5" fill={C.green} />
          <circle cx="680" cy="455" r="5" fill={C.green} />
        </svg>
        <Interactive.Div
          name="Operational Customers entity"
          style={{
            position: "absolute",
            left: 380,
            top: 250,
            width: 240,
            height: 140,
            borderRadius: 16,
            border: "2px solid #A6BEA8",
            background: C.white,
            overflow: "hidden",
            boxSizing: "border-box",
          }}
        >
          <div
            style={{
              padding: "15px 20px",
              fontSize: 28,
              background: "#E6EDE3",
              borderBottom: "1px solid #BCD0BA",
            }}
          >
            Customers
          </div>
          <div style={{ padding: "13px 20px", fontSize: 26, color: C.muted }}>
            Identity
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Operational Orders entity"
          style={{
            position: "absolute",
            left: 740,
            top: 250,
            width: 240,
            height: 140,
            borderRadius: 16,
            border: "2px solid #A6BEA8",
            background: C.white,
            overflow: "hidden",
            boxSizing: "border-box",
          }}
        >
          <div
            style={{
              padding: "15px 20px",
              fontSize: 28,
              background: "#E6EDE3",
              borderBottom: "1px solid #BCD0BA",
            }}
          >
            Orders
          </div>
          <div style={{ padding: "13px 20px", fontSize: 26, color: C.muted }}>
            Order Details
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Operational Products entity"
          style={{
            position: "absolute",
            left: 560,
            top: 455,
            width: 240,
            height: 140,
            borderRadius: 16,
            border: "2px solid #A6BEA8",
            background: C.white,
            overflow: "hidden",
            boxSizing: "border-box",
          }}
        >
          <div
            style={{
              padding: "15px 20px",
              fontSize: 28,
              background: "#E6EDE3",
              borderBottom: "1px solid #BCD0BA",
            }}
          >
            Products
          </div>
          <div style={{ padding: "13px 20px", fontSize: 26, color: C.muted }}>
            Product Catalog
          </div>
        </Interactive.Div>
      </Interactive.Div>

      <Interactive.Div
        name="Illustrative dimensional star model"
        style={{
          position: "absolute",
          inset: 0,
          opacity: interpolate(f, [26 * fps, 27 * fps], [0, 1], motion),
        }}
      >
        <div
          style={{ position: "absolute", left: 370, top: 164, fontSize: 28 }}
        >
          Dimensional Data Model
        </div>
        <svg
          width="1050"
          height="710"
          style={{ position: "absolute", inset: 0 }}
        >
          <path
            d="M480 320V395H570M880 320V395H790M680 463V515"
            fill="none"
            stroke="#BEA376"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <circle cx="570" cy="395" r="5" fill={C.gold} />
          <circle cx="790" cy="395" r="5" fill={C.gold} />
          <circle cx="680" cy="463" r="5" fill={C.gold} />
        </svg>
        <Interactive.Div
          name="Customer dimension"
          style={{
            position: "absolute",
            left: 370,
            top: 220,
            width: 220,
            height: 100,
            borderRadius: 16,
            border: "2px solid #D8C497",
            background: "#FBF6E8",
            padding: "14px 20px",
            boxSizing: "border-box",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 27 }}>Customer</div>
          <div style={{ fontSize: 26, color: C.muted, marginTop: 8 }}>
            Dimension
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Product dimension"
          style={{
            position: "absolute",
            left: 770,
            top: 220,
            width: 220,
            height: 100,
            borderRadius: 16,
            border: "2px solid #D8C497",
            background: "#FBF6E8",
            padding: "14px 20px",
            boxSizing: "border-box",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 27 }}>Product</div>
          <div style={{ fontSize: 26, color: C.muted, marginTop: 8 }}>
            Dimension
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Sales fact table"
          style={{
            position: "absolute",
            left: 570,
            top: 353,
            width: 220,
            height: 110,
            borderRadius: 16,
            border: "2px solid " + C.accent,
            background: "#F0DECE",
            padding: "15px 20px",
            boxSizing: "border-box",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 29, fontWeight: 500 }}>Fact Sales</div>
          <div style={{ fontSize: 26, color: C.accent, marginTop: 10 }}>
            Sales Amount
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Date dimension"
          style={{
            position: "absolute",
            left: 570,
            top: 515,
            width: 220,
            height: 100,
            borderRadius: 16,
            border: "2px solid #D8C497",
            background: "#FBF6E8",
            padding: "14px 20px",
            boxSizing: "border-box",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 27 }}>Date</div>
          <div style={{ fontSize: 26, color: C.muted, marginTop: 8 }}>
            Dimension
          </div>
        </Interactive.Div>
      </Interactive.Div>
      <Interactive.Div
        name="Operational to dimensional modeling path"
        style={{
          position: "absolute",
          left: 370,
          top: 670,
          width: 620,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 24,
          fontSize: 26,
          fontWeight: 600,
          opacity: interpolate(f, [20 * fps, 21 * fps], [0, 1], motion),
        }}
      >
        <span
          style={{
            color: interpolateColors(
              f,
              [25.5 * fps, 26.5 * fps],
              [C.green, C.muted],
            ),
          }}
        >
          Operational
        </span>
        <span style={{ color: C.muted }}>→</span>
        <span
          style={{
            color: interpolateColors(
              f,
              [26 * fps, 27 * fps],
              [C.muted, C.accent],
            ),
          }}
        >
          Dimensional
        </span>
      </Interactive.Div>
    </SplitStage>
  );
};
