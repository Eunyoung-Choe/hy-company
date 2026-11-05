import VideoSummarizer from '@/components/VideoSummarizer';
import PiiLaunchButton from './PiiLaunchButton';

export default function Home() {
  return (
    <>
      <VideoSummarizer />
      {/* 임시: PII Guard 시연 바로가기. 팀원 화면(VideoSummarizer·globals.css)을 건드리지 않게 여기에만 둠 */}
      <PiiLaunchButton />
    </>
  );
}
