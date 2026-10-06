import { Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import { C, Chip, Entity, Frame, Heading, LinkLine, Reveal } from "../design";

export const Models = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const dimensional = f >= 7.5 * fps;
  return (
    <Frame chapter="Common data models" index={6}>
      <Heading kicker={dimensional ? "DIMENSIONAL / GOLD" : "LOGICAL / SILVER"}>
        {dimensional
          ? "Shape data for analysis."
          : "Build a shared operational model."}
      </Heading>
      <Sequence durationInFrames={7.5 * fps} layout="none">
        <Reveal
          at={0.2}
          style={{
            position: "absolute",
            left: 150,
            top: 337,
            display: "flex",
            gap: 30,
          }}
        >
          <Chip>One model across sources</Chip>
          <Chip>Consistent names and keys</Chip>
        </Reveal>
        <LinkLine d="M560 535H655V592H764" at={1.3} />
        <LinkLine d="M1194 650H1290V535H1390" at={2} />
        <Entity
          name="Customer"
          fields={["CustomerID", "CustomerName", "Email"]}
          x={150}
          y={432}
          width={410}
          at={0.5}
        />
        <Entity
          name="OrderLine"
          fields={[
            "OrderLineID",
            "CustomerID",
            "ProductID",
            "Quantity",
            "UnitPrice",
          ]}
          x={764}
          y={432}
          width={430}
          at={0.8}
          accent
        />
        <Entity
          name="Product"
          fields={["ProductID", "ProductName", "Category"]}
          x={1390}
          y={432}
          width={380}
          at={1.1}
        />
        <Reveal
          at={3}
          style={{
            position: "absolute",
            left: 150,
            top: 891,
            fontSize: 30,
            color: C.muted,
          }}
        >
          Customers from the API. Orders from SQL. Products from documents.
        </Reveal>
      </Sequence>
      <Sequence from={7.5 * fps} durationInFrames={7.5 * fps} layout="none">
        <Reveal
          at={0.2}
          style={{
            position: "absolute",
            left: 150,
            top: 337,
            display: "flex",
            gap: 30,
          }}
        >
          <Chip>Grain: one sales line</Chip>
          <Chip>Measure: sales amount</Chip>
        </Reveal>
        <LinkLine d="M560 535H655V592H764" at={1.3} />
        <LinkLine d="M1194 650H1290V535H1390" at={1.8} />
        <LinkLine d="M1194 707H1254V809H980V847" at={2.2} />
        <Entity
          name="DimCustomer"
          fields={["CustomerKey", "CustomerName", "Region"]}
          x={150}
          y={432}
          width={410}
          at={0.3}
        />
        <Entity
          name="FactSales"
          fields={[
            "SalesLineKey",
            "CustomerKey",
            "ProductKey",
            "DateKey",
            "SalesAmount",
          ]}
          x={764}
          y={432}
          width={430}
          at={0.6}
          accent
        />
        <Entity
          name="DimProduct"
          fields={["ProductKey", "ProductName", "Category"]}
          x={1390}
          y={432}
          width={380}
          at={0.9}
        />
        <Reveal
          at={2.1}
          style={{
            position: "absolute",
            left: 764,
            top: 847,
            width: 430,
            textAlign: "center",
            background: C.ink,
            color: C.paper,
            fontSize: 29,
            borderRadius: 10,
            padding: "19px 0",
          }}
        >
          DimDate · DateKey
        </Reveal>
        <Reveal
          at={3}
          style={{
            position: "absolute",
            left: 150,
            top: 823,
            width: 410,
            fontSize: 28,
            lineHeight: 1.5,
            color: C.muted,
          }}
        >
          Analyze sales by customer, product, and date.
        </Reveal>
      </Sequence>
    </Frame>
  );
};
