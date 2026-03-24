import TestingSandbox from "@/components/testing/TestingSandbox";

export const metadata = {
  title: "SecondCortex Testing Sandbox",
  description: "Safe testing playground for agent simulation, firewall redaction, dry-run resurrection, and incident packet debug graph.",
};

export default function TestingPage() {
  return <TestingSandbox />;
}
