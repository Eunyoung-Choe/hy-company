'use client';

import { useState } from 'react';

type Customer = {
  name: string;
  rrn: string;
  phone: string;
  address: string;
  card: string;
  expiry: string;
  cvc: string;
  bank: string;
  account: string;
  otp: string;
};

// 처음 렌더링은 고정값(서버/클라이언트 일치), 버튼을 누르면 무작위 가짜 데이터
const INITIAL: Customer = {
  name: '김하늘',
  rrn: '900101-1234567',
  phone: '010-1234-5678',
  address: '서울특별시 성동구 왕십리로 222 3층',
  card: '4111 1111 1111 1111',
  expiry: '12/29',
  cvc: '123',
  bank: '신한은행',
  account: '110-123-456789',
  otp: '482913',
};

const NAMES = ['이서준', '박지우', '최민서', '정하은', '강도윤', '윤서아', '임시우', '한지민'];
const ADDRS = [
  '서울특별시 강남구 테헤란로 152',
  '경기도 성남시 분당구 판교역로 235',
  '부산광역시 해운대구 센텀중앙로 79',
  '대전광역시 유성구 대학로 99',
  '인천광역시 연수구 송도과학로 32',
];
const BANKS: [string, () => string][] = [
  ['신한은행', () => `110-${d(3)}-${d(6)}`],
  ['KB국민은행', () => `${d(6)}-${d(2)}-${d(6)}`],
  ['우리은행', () => `1002-${d(3)}-${d(6)}`],
  ['하나은행', () => `${d(3)}-${d(6)}-${d(5)}`],
];

const pick = <T,>(a: T[]) => a[Math.floor(Math.random() * a.length)];
const d = (n: number) => Array.from({ length: n }, () => Math.floor(Math.random() * 10)).join('');

function luhnDigit(body: string) {
  let sum = 0;
  for (let i = 0; i < body.length; i++) {
    let n = Number(body[body.length - 1 - i]);
    if (i % 2 === 0) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
  }
  return String((10 - (sum % 10)) % 10);
}

function randomCustomer(): Customer {
  const yy = String(60 + Math.floor(Math.random() * 40));
  const mm = String(1 + Math.floor(Math.random() * 12)).padStart(2, '0');
  const dd = String(1 + Math.floor(Math.random() * 28)).padStart(2, '0');
  const body = pick(['4', '5']) + d(14);
  const card = (body + luhnDigit(body)).replace(/(\d{4})(?=\d)/g, '$1 ');
  const [bank, acct] = pick(BANKS);
  return {
    name: pick(NAMES),
    rrn: `${yy}${mm}${dd}-${pick(['1', '2'])}${d(6)}`,
    phone: `010-${d(4)}-${d(4)}`,
    address: `${pick(ADDRS)} ${1 + Math.floor(Math.random() * 20)}층`,
    card,
    expiry: `${String(1 + Math.floor(Math.random() * 12)).padStart(2, '0')}/${28 + Math.floor(Math.random() * 5)}`,
    cvc: d(3),
    bank,
    account: acct(),
    otp: d(6),
  };
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{value}</span>
    </div>
  );
}

export default function DemoDocs() {
  const [c, setC] = useState<Customer>(INITIAL);

  return (
    <div className="demo">
      <div className="demo-bar" style={{ justifyContent: 'flex-end' }}>
        <button type="button" onClick={() => setC(randomCustomer())}>새 고객 불러오기</button>
      </div>

      <section className="doc">
        <h3>고객 기본정보</h3>
        <Field label="고객명" value={c.name} />
        <Field label="주민등록번호" value={c.rrn} />
        <Field label="연락처" value={c.phone} />
        <Field label="주소" value={c.address} />
      </section>

      <section className="doc">
        <h3>결제 수단</h3>
        <Field label="카드번호" value={c.card} />
        <Field label="유효기간" value={c.expiry} />
        <Field label="CVC" value={c.cvc} />
      </section>

      <section className="doc">
        <h3>환불 계좌</h3>
        <Field label="은행" value={c.bank} />
        <Field label="계좌번호" value={c.account} />
      </section>

      <section className="doc otp">
        <h3>본인 인증</h3>
        <p>OTP {c.otp}</p>
      </section>

      <section className="doc">
        <h3>상담 메모</h3>
        <p>
          고객 {c.name}님 주민번호 {c.rrn} 본인 확인 완료. 환불은 {c.bank} {c.account} 로 진행.
          연락처 {c.phone} 로 결과 안내 예정.
        </p>
      </section>
    </div>
  );
}
