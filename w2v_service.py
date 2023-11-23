from flask import Flask, request
from flask_restful import Api, Resource, reqparse
import gensim
import pickle
import os

model = gensim.models.KeyedVectors.load_word2vec_format('./GoogleNews-vectors-negative300.bin', binary=True)
cached_sim = dict()
pkl_path = "./w2v_sim_cache.pkl"

if os.path.exists(pkl_path ):
    with open(pkl_path , 'rb') as f:
        cached_sim = pickle.load(f)


def w2v_sim(w_from, w_to):
    if (w_from, w_to) in cached_sim:
        return cached_sim[(w_from, w_to)]
    elif (w_to, w_from) in cached_sim:
        return cached_sim[(w_to, w_from)]
    else:
        if w_from.lower() == w_to.lower():
            sim = 1.0
        elif w_from in model.key_to_index and w_to in model.key_to_index:
            sim = model.similarity(w1=w_from, w2=w_to)
        else:
            sim = None
        cached_sim[(w_from, w_to)] = sim
        with open(pkl_path , 'wb') as f:
            pickle.dump(cached_sim, f)
        return sim


'''
def w2v_sent_sim(s_new, s_old):
    # calculate the similarity score matrix
    scores = defaultdict(list)
    for w1 in s_new:
        for w2 in s_old:
            sim = w2v_sim(w1, w2)
            if sim:
                scores[w1].append((w2, sim))

    # sort the similarity in descending order
    for k in scores.keys():
        scores[k] = sorted(scores[k], key=lambda x: x[1], reverse=True)

    num, total_score = 0, 0
    used_words = set()
    for w1 in s_new:
        if w1 in scores:
            for w2, sim in scores[w1]:
                if w2 not in used_words:
                    num += 1
                    total_score += sim
                    used_words.add(w2)
                    break
    return (total_score / num) if num > 0 else None
'''


def w2v_sent_sim(s_new, s_old):
    # calculate the similarity score matrix
    scores = []
    valid_new_words = set()
    valid_old_words = set(s_old)
    for w1 in s_new:
        for w2 in valid_old_words:
            sim = w2v_sim(w1, w2)
            if sim:
                valid_new_words.add(w1)
                scores.append((w1, w2, sim))
    scores = sorted(scores, key=lambda x: x[2], reverse=True)
    counted = []
    for new_word, old_word, score in scores:
        if new_word in valid_new_words and old_word in valid_old_words:
            valid_new_words.remove(new_word)
            valid_old_words.remove(old_word)
            counted.append(score)
        if not valid_new_words or not valid_old_words:
            break
    return sum(counted) / len(counted) if counted else None


class WordSim(Resource):
    def get(self):
        return {'error': 'Non-supported HTTP Method'}, 200

    def post(self):
        args = request.json
        sent_sim = w2v_sent_sim(args['s_new'], args['s_old'])        
        return {'sent_sim': sent_sim}, 200

    def put(self):
        return {'error': 'Non-supported HTTP Method'}, 200

    def delete(self):
        return {'error': 'Non-supported HTTP Method'}, 200


if __name__ == '__main__':
    app = Flask(__name__)
    api = Api(app)
    api.add_resource(WordSim, '/w2v')  # e.g., '/w2v/<string:w1>/<string:w2>'
    app.run(debug=True)
