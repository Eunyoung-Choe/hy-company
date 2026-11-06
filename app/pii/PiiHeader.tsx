import Image from 'next/image';
import BackButton from './BackButton';

/** PII Guard 페이지 공통 머리말. 첫 화면(VideoDigest)의 masthead와 똑같은 구조·스타일.
 *  lead · children: 설명 줄 / 그 아래 줄: 이전 버튼 */
export default function PiiHeader({
  lead,
  children,
  back = true,
}: {
  lead?: React.ReactNode;
  children?: React.ReactNode;
  back?: boolean;
}) {
  return (
    <header className="masthead">
      <h1 className="brand">
        <Image src="/videodigest-logo.png" alt="" width={90} height={90} priority />
        <span>NUNKKAL</span>
      </h1>
      {lead && <p className="pii-lead">{lead}</p>}
      {children && <p className="pii-lead">{children}</p>}
      {back && (
        <div className="pii-head-actions">
          <BackButton />
        </div>
      )}
    </header>
  );
}
