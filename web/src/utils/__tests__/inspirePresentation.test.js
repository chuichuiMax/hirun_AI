import assert from 'node:assert/strict'

import { formatInspireDetailBody } from '../inspirePresentation.js'

assert.equal(
  formatInspireDetailBody(
    [
      '最后希望宝宝们留学之路一切顺利～',
      '',
      '#英国留学生[话题]# #留学英国[话题]# #万能班长留学辅导[话题]# #万能班长课程辅导[话题]# #26fall[话题]#'
    ].join('\n'),
    ['英国留学生', '留学英国', '万能班长留学辅导', '万能班长课程辅导', '26fall']
  ),
  [
    '最后希望宝宝们留学之路一切顺利～',
    '',
    '#英国留学生 #留学英国 #万能班长留学辅导 #万能班长课程辅导 #26fall'
  ].join('\n')
)

assert.equal(
  formatInspireDetailBody('正文内容\n\n#英国留学生 #留学英国', ['英国留学生', '留学英国']),
  '正文内容\n\n#英国留学生 #留学英国'
)

assert.equal(
  formatInspireDetailBody('正文内容\n\n#英国留学生[话题] #留学英国', [
    '英国留学生',
    '留学英国',
    '留学英国'
  ]),
  '正文内容\n\n#英国留学生 #留学英国'
)

assert.equal(formatInspireDetailBody('', ['英国留学生']), '')
assert.equal(formatInspireDetailBody('正文内容', []), '正文内容')
assert.equal(
  formatInspireDetailBody('正文里正常提到 #英国留学生', ['英国留学生']),
  '正文里正常提到 #英国留学生\n\n#英国留学生'
)
assert.equal(
  formatInspireDetailBody('正文内容\n\n#英国留学生 #留学英国。', ['英国留学生', '留学英国']),
  '正文内容\n\n#英国留学生 #留学英国'
)

console.log('inspirePresentation: all assertions passed')
