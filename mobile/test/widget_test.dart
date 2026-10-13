import 'package:abexam_english/core/text.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('answer checking (same rules as the website)', () {
    test('ignores case and punctuation', () {
      expect(grade('i have just come home!', ["I've just come home", 'I have just come home']).ok, isTrue);
    });

    test('accepts a small spelling slip as a typo', () {
      final g = grade('Samarqand is beautiful', 'Samarkand is beautiful');
      expect(g.ok, isTrue);
      expect(g.typo, 'Samarkand is beautiful');
    });

    test('rejects the grammar point itself', () {
      expect(grade('She drink tea', 'She drinks tea').ok, isFalse);
    });

    test('apostrophes may be left out', () {
      expect(grade('I dont know', "I don't know").ok, isTrue);
    });
  });

  test('speech score counts heard words', () {
    final r = speechScore('I was born in May', ['I was born in may']);
    expect(r.score, 1.0);
    final half = speechScore('the cat sat down', ['the dog']);
    expect(half.score, 0.25);
  });

  test('tokens drop punctuation', () {
    expect(tokensOf('Hello, world!'), ['Hello', 'world']);
  });
}
