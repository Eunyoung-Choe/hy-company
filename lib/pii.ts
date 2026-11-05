export const PII_LABELS: Record<string, string> = {
  RRN: '주민등록번호',
  CARD: '카드번호',
  ACCOUNT: '계좌번호',
  CVC_OTP: 'CVC/OTP',
  ADDRESS: '주소',
  PHONE: '휴대폰 번호',
};

export const piiLabel = (k: string) => PII_LABELS[k] ?? k;
