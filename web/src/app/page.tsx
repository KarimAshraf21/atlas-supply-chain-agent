import { Shell } from "@/components/Shell";
import { AtlasProvider } from "@/lib/store";

export default function Home() {
  return (
    <AtlasProvider>
      <Shell />
    </AtlasProvider>
  );
}
