import StatusPoller from "@/components/StatusPoller";

export default function ScanPage({ params }: { params: { id: string } }) {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <StatusPoller scanId={params.id} />
    </div>
  );
}
