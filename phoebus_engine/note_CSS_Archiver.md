# Phoebus RDB Archive Engine（Windows / MySQL）導入〜設定手順まとめ

> 対象: **Native Windows** 上で **Phoebus RDB Archive Engine** を **MySQL** に保存し、**Phoebus Data Browser** で履歴参照できるようにする。

---

## 0. 全体像

- **Archive Engine（バックグラウンド常駐）**が PV を取得して **RDB（MySQL）へ書き込み**。
- **Phoebus Data Browser（GUI）**は **RDB から履歴を読み出して表示**。citeturn40search141  
- MySQL 側は **アーカイブ用テーブル（スキーマ）**が必要（`MySQL.dbd` 相当を投入）。

---

## 1. 必要ファイルの入手

### 1.1 Phoebus GUI（Windows）

- `phoebus-win.zip` を入手（GUI本体）。

### 1.2 Archive Engine（RDB Archive Engine Service）

- `archive-engine.zip` を入手（アーカイブ収集・保存のサービス）。Nightly に配置。citeturn11search71turn11search72  

> Nightly には `archive-engine.zip` が掲載されている。
> <https://controlssoftware.sns.ornl.gov/css_phoebus/nightly/>

---

## 2. NSSM の導入（Windows サービス化に使用）

### 2.1 WinGet で NSSM を導入

```powershell
winget install -e --id NSSM.NSSM
```

WinGet での NSSM 導入例。

### 2.2 NSSM の基本コマンド

- `nssm install <name> <program> [args]` でサービス作成  
- `nssm start/stop/restart/status <name>` で制御  
- NSSM の公式コマンド体系。

---

## 3. MySQL 8.4 の導入と起動

### 3.1 WinGet で MySQL を導入

```powershell
winget install -e --id Oracle.MySQL
```

WinGet で MySQL を導入する例。

### 3.2 MySQL の設定（Configurator）

MSI/Installer 方式では **設定（Configurator）完了までサーバは起動しない**。
（ウィザードを最後まで実施して Windows サービス登録を完了する。）

### 3.3 起動確認

- MySQL classic protocol の既定ポートは **3306/TCP**。

```powershell
Get-Service MySQL84
Test-NetConnection -ComputerName 127.0.0.1 -Port 3306

>> Get-Service MySQL84
>> Test-NetConnection -ComputerName 127.0.0.1 -Port 3306
>> 

Status   Name               DisplayName
------   ----               -----------
Running  MySQL84            MySQL84

ComputerName             : 127.0.0.1                                                  
RemoteAddress            : 127.0.0.1                                                  
ResolvedAddresses        : {127.0.0.1}                                                
PingSucceeded            : False                                                      
PingReplyDetails         :                                                            
TcpClientSocket          :                                                            
TcpTestSucceeded         : True                                                       
RemotePort               : 3306                                                       
TraceRoute               :                                                            
Detailed                 : False                                                      
InterfaceAlias           : Loopback Pseudo-Interface 1                                
InterfaceIndex           : 1                                                          
InterfaceDescription     :                                                            
NetAdapter               :                                                            
NetRoute                 : MSFT_NetRoute (InstanceID = ";?A8:8:8;9??55;55:8:8:8:55;") 
SourceAddress            : 127.0.0.1                                                  
NameResolutionSucceeded  : True                                                       
BasicNameResolution      : {Microsoft.DnsClient.Commands.DnsRecord_PTR}               
LLMNRNetbiosRecords      : {}                                                         
DNSOnlyRecords           : {}                                                         
AllNameResolutionResults : Microsoft.DnsClient.Commands.DnsRecord_PTR                 
IsAdmin                  : False                                                      
NetworkIsolationContext  : Loopback                                                   
MatchingIPsecRules       :                                                            
```

---

## 4. アーカイブ用スキーマ投入（MySQL8 対応）

Phoebus の RDB Archive Engine は、MySQL では **`MySQL.dbd` の SQL を投入してテーブルを作る**前提。citeturn21search122turn21search121  

### 4.1 注意（MySQL 8 では `GRANT ... IDENTIFIED BY` が使えない）

- MySQL 8 以降は **ユーザー作成/更新（CREATE/ALTER USER）と権限付与（GRANT）を分ける**。
- そのため、古い形式の `GRANT ... IDENTIFIED BY` を含むスクリプトは 1064 エラーになる。

### 4.2 `MySQL8.dbd`（修正版）の作成方針

- `MySQL.dbd` の **テーブル作成部分は流用**しつつ、**ユーザー作成部分を MySQL8 形式へ修正**。

例（ローカルのみ運用。パスワードは例）：

```sql
CREATE USER IF NOT EXISTS 'archive'@'localhost' IDENTIFIED BY 'pass';
ALTER USER 'archive'@'localhost' IDENTIFIED BY 'pass';
GRANT ALL PRIVILEGES ON archive.* TO 'archive'@'localhost';

CREATE USER IF NOT EXISTS 'report'@'localhost' IDENTIFIED BY 'pass';
ALTER USER 'report'@'localhost' IDENTIFIED BY 'pass';
GRANT SELECT ON archive.* TO 'report'@'localhost';
FLUSH PRIVILEGES;
```

（GRANT の仕様は MySQL 8.4 の GRANT 文法に従う必要がある。）

### 4.3 PowerShell で SQL を投入する方法

PowerShell は `< file.sql` のリダイレクトが使えないため、**標準入力へパイプ**で流し込む。  

```powershell
Get-Content -Raw .\MySQL8.dbd |
  & "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -h 127.0.0.1 -P 3306 -u root -p 2>&1

```

---

## 5. Archive Engine 設定ファイル（重要）

### 5.1 正しいキー名

Archive Engine が参照する RDB 設定キーは **`org.csstudio.archive/...`**。
（`org.csstudio.archive.rdb/...` ではない。）

### 5.2 `engine_settings.ini` 例（MySQL / localhost）

```ini
org.csstudio.archive/url=jdbc:mysql://127.0.0.1:3306/archive?rewriteBatchedStatements=true
org.csstudio.archive/user=archive
org.csstudio.archive/password=pass
org.csstudio.archive/schema=
```

- 既定例にも `rewriteBatchedStatements=true` が含まれる。

---

## 6. Archive Engine の操作（list / import / run）

```powershell
Get-Content -Raw init_archive.sql |
  & "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -h 127.0.0.1 -P 3306 -u root -p 2>&1

```

### 6.1 設定一覧

```powershell
java -jar .\service-archive-engine-4.7.4-SNAPSHOT.jar `
  -settings .\engine_settings.ini `
  -list
```

### 6.2 PV 設定（engineconfig.xml）を取り込み

```powershell
java -jar .\service-archive-engine-4.7.4-SNAPSHOT.jar `
  -settings .\engine_settings.ini `
  -import .\engineconfig.xml `
  -engine Main
```

### 6.3 実行

```powershell
java -jar .\service-archive-engine-4.7.4-SNAPSHOT.jar `
  -settings .\engine_settings.ini `
  -import .\engineconfig.xml `
  -engine Main `
  -replace_engine
```

```powershell
& "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -h 127.0.0.1 -P 3306 -u root -p
& "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -h 127.0.0.1 -P 3306 -u report -p 


& "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe" `
  -u root -p --no-data archive > archive_full.sql
```

```powershell
nssm restart PhoebusArchiveEngine
```

```sql
USE archive;
SHOW TABLES;
```

```sql
USE archive;
SELECT COUNT(*) FROM channel;
SELECT COUNT(*) FROM sample;
SELECT NOW() AS mysql_now;

USE archive;
SELECT MAX(smpl_time) AS db_last_time FROM sample;
SELECT MAX(s.smpl_time) AS ioc_last_time
FROM sample s JOIN channel c ON c.channel_id=s.channel_id
WHERE c.name LIKE 'IOC-APP1:%';

SELECT c.name, MAX(s.smpl_time) AS last_time
FROM sample s
JOIN channel c ON c.channel_id = s.channel_id
WHERE c.name='IOC-APP1:line:a';

USE archive;
SELECT MIN(s.smpl_time) AS first_time,
       MAX(s.smpl_time) AS last_time,
       COUNT(*)         AS samples
FROM sample s
JOIN channel c ON c.channel_id = s.channel_id
WHERE c.name='IOC-APP1:line:a';

```

---

## 7. バックグラウンド（サービス）で動かす（NSSM）

### 7.1 サービス登録（例）

> 端末入力（対話シェル）があると EOF で終了することがあるため、`-noshell` を付けて実行。

```powershell
$svc = "PhoebusArchiveEngine"
$dir = "C:\Users\Nakai\archive-engine-4.7.4-SNAPSHOT"
$java = (Get-Command java).Source
$jar  = Join-Path $dir "service-archive-engine-4.7.4-SNAPSHOT.jar"
$ini  = Join-Path $dir "engine_settings.ini"

# 既存サービスがあれば削除して作り直す
nssm stop   $svc 2>$null
nssm remove $svc confirm 2>$null

# 1) まず “java.exe を実行するサービス” として作成（引数はここで渡さない）
nssm install $svc $java

# 2) 作業ディレクトリ
nssm set $svc AppDirectory $dir

# 3) 引数（AppParameters）を NSSM に確実に保存
#    -jar / -settings / -engine / -noshell が丸ごと入るように " でパスを囲む
$nssmArgs = "-jar `"$jar`" -settings `"$ini`" -engine Main -noshell"
nssm set $svc AppParameters $nssmArgs

# 4) ログ（stdout/stderr）
nssm set $svc AppStdout (Join-Path $dir "archive-engine.out.log")
nssm set $svc AppStderr (Join-Path $dir "archive-engine.err.log")

# 5) 起動
nssm start  $svc
nssm status $svc
```

NSSM の install/start/status などのコマンドは公式に定義されている。

---

## 8. Phoebus Data Browser で履歴を見る設定

Data Browser 側は JDBC を `org.csstudio.trends.databrowser3/urls` 等に設定する（MySQL の例がドキュメントにある）。
例（Phoebus の settings.ini へ追記）：

```ini
org.csstudio.trends.databrowser3/urls=jdbc:mysql://127.0.0.1:3306/archive|RDB
org.csstudio.trends.databrowser3/archives=jdbc:mysql://127.0.0.1:3306/archive|RDB
```

---

## 9. つまずきポイント（今回の学び）

1) **MySQL 8 は `GRANT ... IDENTIFIED BY` が使えない** → CREATE/ALTER USER と GRANT に分離。
2) **Archive Engine の RDB 設定キーは `org.csstudio.archive/...`**。
3) PowerShell は `< file.sql` が使えないため **`Get-Content -Raw | mysql.exe`** で投入。  
4) サービス化は NSSM が簡単（install/start/status）。

---

## 10. 次にやること（運用向け）

- `pass` は弱いので、運用時は強いパスワードに変更し、`engine_settings.ini` も同じ値に合わせる。

```sql
mysql> SHOW CREATE EVENT delete_old_samples;
+--------------------+----------+-----------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------+----------------------+--------------------+
| Event              | sql_mode | time_zone | Create Event                                                                                                                                                                                                        | character_set_client | collation_connection | Database Collation |
+--------------------+----------+-----------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------+----------------------+--------------------+
| delete_old_samples |          | SYSTEM    | CREATE DEFINER=`root`@`localhost` EVENT `delete_old_samples` ON SCHEDULE EVERY 1 HOUR STARTS '2026-05-18 16:37:47' ON COMPLETION NOT PRESERVE ENABLE DO DELETE FROM sample
WHERE smpl_time < NOW() - INTERVAL 1 DAY | cp932                | cp932_japanese_ci    | utf8mb4_0900_ai_ci |
+--------------------+----------+-----------+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------+----------------------+--------------------+
1 row in set (0.00 sec)
```
