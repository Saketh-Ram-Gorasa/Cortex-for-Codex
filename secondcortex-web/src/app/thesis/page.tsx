export const metadata = {
  title: "SecondCortex Thesis",
  description: "SecondCortex thesis document.",
};

export default function ThesisPage() {
  return (
    <main style={{ minHeight: "100vh", background: "#0b0f14", paddingTop: "84px" }}>
      <iframe
        title="SecondCortex Thesis"
        src="/secondcortex_thesis.html"
        style={{
          width: "100%",
          height: "calc(100vh - 84px)",
          border: "0",
          display: "block",
          background: "#f5f2eb",
        }}
      />
    </main>
  );
}
