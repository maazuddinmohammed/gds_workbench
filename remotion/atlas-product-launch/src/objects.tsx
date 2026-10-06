import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { C, ease } from "./design";

/** Reusable illustrations of real source shapes; all content is fictional. */
export function SourceObject({
  kind,
  width = 400,
}: {
  kind: "sql" | "nosql" | "stream" | "api" | "folder" | "files";
  width?: number;
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pulse = (f / fps) % 3;
  return (
    <svg
      width={width}
      height={width * 0.6}
      viewBox="0 0 400 240"
      fill="none"
      style={{ overflow: "visible" }}
    >
      {kind === "sql" ? (
        <>
          <path
            d="M36 64V174C36 205 169 205 169 174V64"
            fill="#D8E5DB"
            stroke="#6A8C79"
            strokeWidth="2"
          />
          <ellipse
            cx="102.5"
            cy="64"
            rx="66.5"
            ry="26"
            fill="#EAF0E6"
            stroke="#6A8C79"
            strokeWidth="2"
          />
          <path
            d="M36 105C36 136 169 136 169 105M36 146C36 177 169 177 169 146"
            stroke="#6A8C79"
            strokeWidth="2"
          />
          <rect
            x="130"
            y="96"
            width="241"
            height="125"
            rx="10"
            fill={C.white}
            stroke="#95AF9C"
            strokeWidth="2"
          />
          <path
            d="M130 135H371M130 176H371M210 96V221M291 96V221"
            stroke="#CBD8C9"
            strokeWidth="2"
          />
          <path
            d="M140 97H361Q370 97 370 108V135H131V107Q131 97 140 97"
            fill="#527E66"
          />
          <text x="147" y="123" fontSize="18" fill="white">
            ID
          </text>
          <text x="223" y="123" fontSize="18" fill="white">
            Date
          </text>
          <text x="302" y="123" fontSize="18" fill="white">
            Total
          </text>
          <text x="146" y="162" fontSize="18" fill={C.ink}>
            1042
          </text>
          <text x="223" y="162" fontSize="18" fill={C.muted}>
            10/05
          </text>
          <text x="305" y="162" fontSize="18" fill={C.muted}>
            128
          </text>
          <text x="146" y="204" fontSize="18" fill={C.ink}>
            1043
          </text>
          <text x="223" y="204" fontSize="18" fill={C.muted}>
            10/05
          </text>
          <text x="305" y="204" fontSize="18" fill={C.muted}>
            216
          </text>
        </>
      ) : null}
      {kind === "nosql" ? (
        <>
          <rect
            x="91"
            y="25"
            width="258"
            height="187"
            rx="12"
            fill="#D9D4E9"
            stroke="#A59BBF"
            transform="rotate(7 220 120)"
          />
          <rect
            x="63"
            y="40"
            width="258"
            height="187"
            rx="12"
            fill={C.white}
            stroke="#A59BBF"
            strokeWidth="2"
          />
          <text
            x="83"
            y="83"
            fontSize="28"
            fill="#796B9C"
            fontFamily="IBM Plex Mono"
          >
            {"{ product }"}
          </text>
          <text
            x="84"
            y="123"
            fontSize="19"
            fill={C.ink}
            fontFamily="IBM Plex Mono"
          >
            {'"id": "P-021",'}
          </text>
          <text
            x="84"
            y="156"
            fontSize="19"
            fill={C.ink}
            fontFamily="IBM Plex Mono"
          >
            {'"name": "Linen",'}
          </text>
          <text
            x="84"
            y="189"
            fontSize="19"
            fill={C.ink}
            fontFamily="IBM Plex Mono"
          >
            {'"category": "Home"'}
          </text>
        </>
      ) : null}
      {kind === "stream" ? (
        <>
          <path d="M12 131H389" stroke="#A5C0CB" strokeWidth="3" />
          {[0, 1, 2, 3].map((i) => {
            const x = 18 + (((f / fps) * 37 + i * 94) % 355);
            return (
              <g key={i} opacity={0.45 + 0.5 * Math.sin((x / 400) * Math.PI)}>
                <rect
                  x={x}
                  y="111"
                  width="36"
                  height="40"
                  rx="8"
                  fill="#759FAB"
                />
                <path d={`M${x + 11} 130h14`} stroke="white" strokeWidth="2" />
              </g>
            );
          })}
          <rect
            x="91"
            y="25"
            width="222"
            height="58"
            rx="10"
            fill={C.white}
            stroke="#A6BDC6"
          />
          <text
            x="112"
            y="61"
            fontSize="24"
            fill="#527D8D"
            fontFamily="IBM Plex Mono"
          >
            order.created
          </text>
          <path d="M199 84V103" stroke="#759FAB" strokeWidth="2" />
          <rect x="90" y="182" width="220" height="39" rx="19" fill="#E0EAF0" />
          <circle
            cx="114"
            cy="202"
            r={4 + Math.sin((f / fps) * 2) * 1.5}
            fill="#527D8D"
          />
          <text x="130" y="209" fontSize="20" fill="#527D8D">
            Continuous events
          </text>
        </>
      ) : null}
      {kind === "api" ? (
        <>
          <rect x="22" y="28" width="340" height="88" rx="12" fill={C.ink} />
          <rect x="39" y="46" width="67" height="42" rx="7" fill="#5F9277" />
          <text
            x="49"
            y="75"
            fontSize="24"
            fill="white"
            fontFamily="IBM Plex Mono"
          >
            GET
          </text>
          <text
            x="123"
            y="75"
            fontSize="24"
            fill={C.paper}
            fontFamily="IBM Plex Mono"
          >
            /customers
          </text>
          <path
            d="M310 116V139H82V153"
            stroke="#8CAB98"
            strokeWidth="2"
            strokeDasharray="6 5"
            strokeDashoffset={-f / 4}
          />
          <rect
            x="56"
            y="149"
            width="315"
            height="77"
            rx="12"
            fill={C.white}
            stroke="#A8BDAD"
            strokeWidth="2"
          />
          <circle
            cx="87"
            cy="187"
            r="8"
            fill={pulse > 1 ? C.green : "#AAB7AC"}
          />
          <text
            x="109"
            y="195"
            fontSize="21"
            fill={C.ink}
            fontFamily="IBM Plex Mono"
          >
            200 · JSON response
          </text>
        </>
      ) : null}
      {kind === "folder" ? (
        <>
          <path
            d="M48 72V49Q48 36 63 36H150L174 62H336Q353 62 353 81V207H48Z"
            fill="#D2A06D"
            stroke="#A87845"
            strokeWidth="2"
          />
          <path d="M99 28H176L195 49V177H99Z" fill={C.white} stroke="#BFBCAB" />
          <path
            d="M218 39H285L305 59V173H218Z"
            fill={C.white}
            stroke="#BFBCAB"
          />
          <path
            d="M112 68H179M112 86H169M232 82H291M232 100H281"
            stroke="#A6B6A6"
            strokeWidth="4"
          />
          <path
            d="M28 99Q25 89 40 89H350Q368 89 363 105L342 213H51Z"
            fill="#E9C99B"
            stroke="#C19A63"
            strokeWidth="2"
          />
          <text
            x="83"
            y="161"
            fontSize="27"
            fill="#745333"
            fontFamily="IBM Plex Mono"
          >
            /store-exports
          </text>
          <text x="83" y="190" fontSize="18" fill="#8E6B46">
            Daily extracts
          </text>
        </>
      ) : null}
      {kind === "files" ? (
        <>
          {[
            ["CSV", "#4B8065", 28, -7],
            ["XLSX", "#638F77", 146, 3],
            ["JSON", "#AA805D", 264, 8],
          ].map(([name, color, x, angle]) => (
            <g
              key={name}
              transform={`translate(${x},24) rotate(${angle},56,100)`}
            >
              <path
                d="M0 12Q0 0 12 0H79L113 35V184Q113 198 99 198H12Q0 198 0 184Z"
                fill={C.white}
                stroke="#C9CABC"
                strokeWidth="2"
              />
              <path d="M79 0V35H113" fill="#E8EBDD" />
              <rect
                x="-6"
                y="53"
                width="109"
                height="45"
                rx="5"
                fill={String(color)}
              />
              <text
                x="8"
                y="83"
                fontSize="25"
                fill="white"
                fontFamily="IBM Plex Mono"
              >
                {name}
              </text>
              <path
                d="M17 122H91M17 143H91M17 164H69"
                stroke="#C8D3C7"
                strokeWidth="5"
              />
            </g>
          ))}
        </>
      ) : null}
    </svg>
  );
}

/** Animated pointer is a movie layer, never an action against the live application. */
export function Pointer({
  times,
  x,
  y,
  clicks = [],
}: {
  times: number[];
  x: number[];
  y: number[];
  clicks?: number[];
}) {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = f / fps;
  const click = clicks.find((t) => local >= t && local < t + 0.5);
  return (
    <div
      style={{
        position: "absolute",
        left: interpolate(local, times, x, ease),
        top: interpolate(local, times, y, ease),
        pointerEvents: "none",
        zIndex: 10,
        opacity: interpolate(
          local,
          [
            times[0],
            times[0] + 0.15,
            times[times.length - 1] + 0.3,
            times[times.length - 1] + 0.6,
          ],
          [0, 1, 1, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        ),
      }}
    >
      {click !== undefined ? (
        <div
          style={{
            position: "absolute",
            left: -22,
            top: -22,
            width: 44,
            height: 44,
            border: `2px solid ${C.accent}`,
            borderRadius: "50%",
            scale: 1 + (local - click) * 3,
            opacity: 1 - (local - click) * 2,
          }}
        />
      ) : null}
      <svg width="38" height="48" viewBox="0 0 38 48">
        <path
          d="M3 2V36L12 29L20 45L29 40L21 25L35 23Z"
          fill={C.ink}
          stroke="white"
          strokeWidth="2.5"
        />
      </svg>
    </div>
  );
}
