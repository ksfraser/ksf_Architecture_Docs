
## 7. 11 shared-doc holders are detached (deliberately NOT re-linked)

`AGENTS_ARCH.md` has **195 holders**, of which **184 share the canonical
inode** and **11 are independent copies** left behind when their repos ran
`git checkout` / `git reset --hard` — those replace the inode, silently
breaking the hardlink.

Detached (do NOT re-link without checking for local edits first — re-linking
overwrites their content with the canonical version):

- `ksf_ProjectManagement`, `ksf_ModulesDAO`, `ksf_FA_Assets`,
  `ksf_FA_Timeshets`, `ksf_FA_Mail`, `FA_ProductAttributes`,
  `ksf_FA_Woocommerce`, `ksf_FA_CRM_Opportunities`, `ksf_FA_CRM_Tags`,
  `ksf_FA_CRM_Territories`, `ksf_FA_InventoryCount`

Note three of those (`ksf_FA_CRM_Opportunities`, `_Tags`, `_Territories`) share
one inode *with each other* — they are a detached cluster, not independent.

**Left detached on purpose (2026-10-11).** Merging or re-attaching needs a
decision on whether the canonical version may overwrite local edits in those
repos. Defer until that is established.
