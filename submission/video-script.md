# CrewVoice — сценарий демо-видео

**Хронометраж:** 2:30. **Язык озвучки:** английский (судьи — AssemblyAI, Meta, Amazon, Zocdoc).
**Формат:** запись экрана 1280×720, лицо в кадре не нужно, голос твой — он же и есть демо.

Реплики, отмеченные **VO**, читаются за кадром. Реплики **SAY** произносятся в микрофон агенту —
они должны быть слышны в записи как живая речь, не как закадровый текст.

---

## 0:00–0:20 · Боль

**На экране:** таблица Excel с табелем, курсор водит по строке; рядом открыт чат/смс с прорабом.

> **VO:** "End of the month on a construction site. Payroll has a number for Jose.
> Jose says the number is wrong. The only record of what was actually said is a
> foreman's memory and a smudged notebook. Somebody is going to lose this argument
> without any evidence."

**Не говорить:** никакой статистики про «X миллиардов теряется на ошибках» — цифру не проверить,
судьи ловят такое сразу.

---

## 0:20–0:35 · Что это

**На экране:** открывается CrewVoice, пустая таблица, курсор на кнопке Start talking.

> **VO:** "CrewVoice takes the foreman's spoken end-of-day report and turns it into a
> timesheet that can be audited line by line. It runs on AssemblyAI's Voice Agent API —
> speech in, speech out, tool calls in the middle."

---

## 0:35–1:05 · Обычный проход

**Нажимаешь Start talking. Говоришь в микрофон.**

> **SAY:** "Jose worked nine hours today."

**Агент отвечает голосом** («José Ramírez, nine hours — is that right?»), в таблице появляется
**жёлтая pending-строка**. Задержись на ней курсором — зритель должен увидеть слово `pending`.

> **SAY:** "Yes."

Строка становится зелёной, `confirmed`.

> **VO:** "Nine hours is now on the sheet — but only because I said yes out loud.
> Until then it sat in pending, outside payroll."

---

## 1:05–1:35 · Три отказа подряд (ядро видео)

Говорить подряд, без пауз на объяснения — объяснение идёт поверх.

> **SAY:** "Miguel worked twenty hours."

Агент отказывается, в логе — оранжевая строка `record_hours → refused: out_of_range`.

> **SAY:** "Bobby worked eight hours."

Агент переспрашивает, кто это, и называет кандидатов из списка бригады.

> **SAY:** "Luis trabajó ocho horas." → агент отвечает по-испански → **SAY:** "Sí."

> **VO:** "Twenty hours in a day is a mishearing, not a shift. A name that is not on the
> crew list is a question, never a guess. And the crew switches to Spanish mid-shift,
> so the agent does too. None of these three rules live in the prompt — they live in the
> tools, which is why the model cannot talk its way past them."

---

## 1:35–2:05 · Доказательство

**На экране:** колонка HEARD AS — строка `José Ramírez` с пометкой `Jose`. Наведи курсор,
всплывает исходная фраза.

> **VO:** "Speech recognition wrote 'Jose'. Payroll has 'José' with an accent. Same man —
> the roster match folds both to the same key, and the sheet keeps what was actually heard."

**Нажимаешь Export CSV**, открываешь файл.

> **VO:** "The export carries two extra columns: what recognition heard, and the sentence
> it came from. When Jose disputes his hours, the argument is settled by the record instead
> of by whoever remembers harder. And rows nobody confirmed are simply not in this file."

---

## 2:05–2:30 · Финал

**На экране:** схема из README (браузер → мост → AssemblyAI → инструменты → CSV), потом логотип KHLab.

> **VO:** "Voice Agent API for the conversation, a tool layer that refuses to write anything
> it was not told to confirm. Built in three weeks, running on a free instance, ready for a
> crew of six or six hundred. CrewVoice — the foreman talks, payroll gets numbers it can prove."

---

## Чек-лист перед записью

- [ ] Ключ AssemblyAI в `.env`, запуск **без** `CREWVOICE_MOCK` — в кадре не должно быть плашки
      «scripted agent (no API key)».
- [ ] Render-инстанс разбужен за 5 минут до записи (бесплатный спит, просыпается ~50 с).
- [ ] Таблица пустая: перезапусти сервер, чтобы сессия была чистой.
- [ ] Зум браузера 125% — судья смотрит на телефоне, мелкий текст не читается.
- [ ] Внешний микрофон или гарнитура: качество твоего голоса судьи прочтут как качество продукта.
- [ ] Снять два-три дубля живого прохода. Если агент в дубле ошибётся — не переснимай молча,
      возьми дубль, где он **переспросил**: это и есть заявленное поведение.
- [ ] Длительность ≤ 3:00, залить на YouTube как unlisted, ссылку в сабмит.

## Что говорить не надо

- «Мы используем самые передовые модели ИИ» — судьи сами делают эти модели.
- Обещания про будущие фичи: оценивают то, что видно в кадре.
- Извинения за простой дизайн. Табель и должен выглядеть как табель.
