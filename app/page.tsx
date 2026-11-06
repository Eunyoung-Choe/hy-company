import VideoSummarizer from '@/components/VideoSummarizer';
import PiiLaunchButton from './PiiLaunchButton';

export default function Home() {
  // PII Guard 시연 바로가기는 소개 문구 줄 오른쪽 끝에 배치
  return <VideoSummarizer headerAction={<PiiLaunchButton />} />;
}
