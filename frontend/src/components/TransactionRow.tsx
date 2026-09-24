import type { Account, Transaction } from "../api/types";
import { categoryLabel, type CategoryMap } from "../lib/categories";
import { ltr } from "../lib/format";
import { Money } from "./Money";

interface Props {
  txn: Transaction;
  categories: CategoryMap;
  account?: Account;
  onSelect?: (txn: Transaction) => void;
}

export function TransactionRow({ txn, categories, account, onSelect }: Props) {
  const uncategorized = txn.category_id === null;
  const content = (
    <>
      <span className="list-row-main">
        <span className="list-row-title">{txn.description}</span>
        <span className="list-row-sub">
          <span className={uncategorized ? "tag-uncategorized" : undefined}>{categoryLabel(txn.category_id, categories)}</span>
          {account && ` · ${account.institution_label} ${ltr(account.account_number)}`}
        </span>
      </span>
      <span className="list-row-end">
        <Money value={txn.amount} decimals={2} className={Number(txn.amount) > 0 ? "pos" : undefined} sign={Number(txn.amount) > 0 ? "always" : "auto"} />
      </span>
    </>
  );
  if (!onSelect) return <div className="list-row">{content}</div>;
  return (
    <button type="button" className="list-row" onClick={() => onSelect(txn)}>
      {content}
    </button>
  );
}
